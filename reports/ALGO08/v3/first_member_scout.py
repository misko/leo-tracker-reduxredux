"""Measure the twelve observed shorter-scout omissions in the full saved weak packet."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from preloaded_saved_worker import read, write


SCOUT = Path("/dev/shm/leo-v3-all-visit-timing-0016-01")
FULL = Path("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms")
RESULT_PIN = "b1a7727ffb35afe91e6e6886b2ea35654f7a4eea4847a0ce85adf9cc22c9b333"
FULL_PIN = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
RECIPE_PIN = "70594e676776ac7f1a12464865f7118c05b0126b236a2bed73616c0b8407ac1a"
OWNER_PIN = "69dfd49a08bbf72a8a8957589f6aa66ba7da70475d05d29593b62645fb60fe1b"
SCOPE_PINS = (
    ("d7581adb0b28bf7e4a121980410f08a4d31ac362352c46b4940a3d8a208e9bf2",
     "c1d86d2640a4e087874e2cba692ae3fe1b2cab98a6b3c88a2a4d0298b0665fbc"),
    ("25e20e5e44d5f7726394a06e69fa0aafaa338a709068e074513df87031446566",
     "94544439cf0899de04ba1e34d5046f086e45375db231927316dc27f1f5d132c5"),
)
MODES = ("ordinary", "shorter")
ARMS = ("c0", "fitted_c")
ISSUED = 64
SCORES = ("fractional_exact_score", "fractional_control_score", "fractional_margin")
SCORE_TOLERANCE = 1e-10
PUBLICATION = "first-member-publication.json"


def metadata(row):
    return {key: value for key, value in row.items() if key != "candidates"}


def splice(full, ordinary, shorter, anchor_lanes):
    """Leave the original measurement untouched wherever both guarded calls agree."""
    peak = dict.fromkeys(SCORES, 0.0)
    changed, updated = [], []
    for original, reference, test in zip(full, ordinary, shorter, strict=True):
        if metadata(original) != metadata(reference) or metadata(reference) != metadata(test):
            raise ValueError("Unmatched chronological lane")
        a, b, c = (row["candidates"] for row in (original, reference, test))
        if len(a) != len(b) or len(a) > 1:
            raise ValueError("The ordinary member differs in factor cardinality")
        for first, second in zip(a, b, strict=True):
            if any(first[k] != second[k] for k in first.keys() | second.keys() if k not in SCORES):
                raise ValueError("The ordinary member changed an exact signed factor field")
            for field in SCORES:
                delta = abs(first[field] - second[field])
                if not isfinite(delta) or delta > SCORE_TOLERANCE:
                    raise ValueError("The ordinary member exceeded the earlier score certificate")
                peak[field] = max(peak[field], delta)
        if b == c:
            updated.append(original)
            continue
        lane = original["visit_index"], original["receiver_id"]
        if lane in anchor_lanes or not b or c:
            raise ValueError("Unexpected first-member change beyond measured short-lane omissions")
        changed.append(original)
        updated.append(dict(original, candidates=c))
    return updated, changed, peak


def observation_id(session, row):
    token = f'{session}:{row["receiver_id"]}:{row["valid_start_counter"]}'
    return "sha256:" + sha256(token.encode()).hexdigest()


def bind_inputs():
    from anchor_exposure import enroll
    from empty_bootstrap import bind_native, checked
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file

    full = json.loads(checked(native_file(FULL), FULL_PIN))
    baseline = json.loads(checked(FULL/"full-short-recipe.json", RECIPE_PIN))
    recipe = baseline["recipe"]
    source = full["source"]
    session, manifest = source["session_id"], source["input_manifest_sha256"]
    bind_native(full, session, manifest, canonical_digest(recipe)[7:], expected="sha256:"+FULL_PIN)
    inventory = json.loads(checked(FULL/"fast-scan-inputs"/(session+".json"), manifest[7:]))
    result = json.loads(checked(SCOUT/"result.json", RESULT_PIN))
    member = result["member"]
    if (baseline["saved_digest"] is not None or inventory["window_count"] != 808
            or member["chunk_index"] != 0 or member["first_sequence"] != 0
            or member["window_count"] != ISSUED or result["north_eligible"]):
        raise ValueError("Inputs are outside the original failed first-member gate")
    scopes, rows = {}, {}
    for j, pins in enumerate(SCOPE_PINS):
        for mode, pin in zip(MODES, pins, strict=True):
            entry = SCOUT/f"{j}-{mode}"
            scope = json.loads(checked(entry/"scope-receipt.json", pin))
            published = json.loads(checked(entry/"detections.json", scope["native_sha256"][7:]))
            witness = result["pairs"][j]["runs"][mode]
            pin_input = scope["prefix_inventory"]
            held = scope["held_choice"]
            bind_native(published, held["session"], pin_input, held["selected_recipe_sha256"][7:],
                        expected=scope["native_sha256"])
            if (witness["clock"]["exit_code"] or witness["native"] != published or witness["scope"] != scope
                    or scope["scope"]["segments"][0]["manifest_digest"] != inventory["segments"][0]["manifest_digest"]
                    or scope["position_runs"] or len(scope["iq"]) != ISSUED
                    or {f["name"]: [f["bytes"], f["sha256"]] for f in scope["opened"]} != result["original"]
                    or pin_input != held["input_inventory"] or held["selected_native_sha256"] != scope["native_sha256"]
                    or canonical_digest([pin_input, scope["iq"]]) != published["source"]["raw_recording_authority_digest"]
                    or canonical_digest(scope["original_probes"]) != held["pre_refinement_probes_sha256"]
                    or published["clock_anchor"] != full["clock_anchor"]
                    or published["delivery_clocks"] != full["delivery_clocks"][:ISSUED]
                    or {k: scope["recipe"][k] for k in recipe} != recipe):
                raise ValueError("Lost exact scope, attribution or pre-tail evidence")
            if mode in rows and (scope["original_probes"] != rows[mode] or scope["iq"] != scopes[mode]["iq"]):
                raise ValueError("The reversal did not reproduce the same signed measurement")
            rows[mode], scopes[mode] = scope["original_probes"], scope
    a, b = (scopes[mode] for mode in MODES)
    if (any(a[k] != b[k] for k in ("iq", "opened", "prefix_inventory", "original_segment_inventory"))
            or {k:v for k,v in b["recipe"].items() if k != "short_timing_scout"} != a["recipe"]
            or b["recipe"]["short_timing_scout"]["pack_sha256"] != result["pack_sha256"]):
        raise ValueError("The scope pair does not differ only by its guarded timing scout")
    probes = source["probes"]
    prefix = [row for row in probes if row["visit_index"] < ISSUED]
    anchors = {(visit, radio) for visit, _, radio, _, kind, _ in enroll(full) if kind == "anchor"}
    replacement, missing, certificate = splice(prefix, rows["ordinary"], rows["shorter"], anchors)
    if len(missing) != 12 or len(probes) != 1426 or len(prefix) != 116 or probes[:len(prefix)] != prefix:
        raise ValueError("Saved evidence differs from the frozen physical prefix size and census")
    owner_receipt = json.loads(checked(FULL/"joint-research-receipt.json", OWNER_PIN))
    receipt = owner_receipt["receipt"]
    owners = owner_receipt["selected_rows"]
    detail = FastStandardAnalysisStore(FULL).detail(receipt["run_id"])
    if (detail["input_sha256"] != "sha256:"+FULL_PIN or detail["terminal_sha256"] != receipt["terminal_sha256"]
            or any(canonical_digest({row[0]: row[1] for row in owners[k]}) != detail["arms"][k]["owner_sha256"] for k in ARMS)):
        raise ValueError("Published owner rosters do not bind the unrefined full input")
    ids = {observation_id(session, row): row for row in missing}
    audit = dict(
        ordinary_probes_sha256=a["held_choice"]["pre_refinement_probes_sha256"],
        shorter_probes_sha256=b["held_choice"]["pre_refinement_probes_sha256"],
        full_native_sha256="sha256:"+FULL_PIN, full_receipt_sha256=OWNER_PIN,
        scout_result_sha256=RESULT_PIN, physical_scope_pins=SCOPE_PINS,
        member=member, certificate=certificate, lost_by_radio=dict(Counter(row["receiver_id"] for row in missing)),
        factor_losses=[dict(metadata(row), observation_id=identifier, candidates=row["candidates"])
                       for identifier, row in ids.items()],
        baseline_owner_counts={k: len(owners[k]) for k in ARMS},
        joined_owner_rows={k: [row for row in owners[k] if row[0] in ids] for k in ARMS},
    )
    alternate = dict(recipe, first_member_scout=dict(
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        parent_native_sha256="sha256:"+FULL_PIN, parent_detector_sha256=canonical_digest(recipe),
        paired_scope_sha256=SCOPE_PINS[0], member=member, guarded_native=b["recipe"]["short_timing_scout"],
        pre_tail_probes_sha256=audit["shorter_probes_sha256"],
        measurement="observed first-member pre-tail omissions; original full packet on all other lanes",
    ))
    return full, recipe, alternate, replacement + probes[len(prefix):], audit


def choose(native, recipe):
    from anchor_cycle_route import select_route
    from anchor_exposure import bind
    from anchor_holds import history_rows
    from continued_cfo_trial import rebinding
    from empty_bootstrap import CONTINUATION, EXTRA_SOURCES, bind_native, checked, clock, now
    from held_anchor_route_publication import SELECTOR_SOURCES, SETTINGS
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants import carrier_continuation

    start = now()
    for name, pin in SELECTOR_SOURCES.items():
        checked(HERE/name, pin)
    continued = EXTRA_SOURCES[CONTINUATION]
    checked(Path(carrier_continuation.__file__), continued)
    choice = select_route(native)
    rows = native["source"]["probes"]
    output, spec = native, recipe
    if choice["route"] == "history":
        spec = dict(recipe, unrefined_held_history=dict(settings=SETTINGS, sources=SELECTOR_SOURCES, continuation=continued))
        output = rebinding(native, history_rows(rows), spec)
        bind(native, output)
    source = native["source"]
    detector, digest = canonical_digest(spec), canonical_digest(output)
    bind_native(output, source["session_id"], source["input_manifest_sha256"], detector[7:], expected=digest)
    return output, dict(choice=choice, recipe=spec, input=canonical_digest(native), native_sha256=digest,
                        detector_recipe_sha256=detector, clock=clock(start), measured=sum(bool(r["candidates"]) for r in rows),
                        selected=sum(bool(r["candidates"]) for r in output["source"]["probes"]), cfo_refinement_calls=0)


def prepare(root):
    from continued_cfo_trial import rebinding
    from empty_bootstrap import checked, clock, now
    from leo.storage.fast_scan import immutable_json

    start = now()
    full, recipe, alternate, rows, audit = bind_inputs()
    audit["input_and_splice_clock"] = clock(start)
    for mode, native, spec in (("ordinary", full, recipe), ("shorter", rebinding(full, rows, alternate), alternate)):
        packet, choice = choose(native, spec)
        path = root/f"{mode}-detections.json"
        immutable_json(path, packet)
        checked(path, choice["native_sha256"][7:])
        write(root/f"{mode}-selection.json", choice)
    write(root/"prepared.json", dict(audit=audit, total=clock(start)))


def worker(root, mode):
    import empty_bootstrap as staged
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from preloaded_saved_worker import enrolled
    from raw_cfo_north_trial import ORDER, publish_saved

    began = staged.now()
    selected = read(root/f"{mode}-selection.json")
    path = root/f"{mode}-detections.json"
    packet = json.loads(staged.checked(path, selected["native_sha256"][7:]))
    orbit, rank = {}, {}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        runtime = staged.load_runtime()
        request, archive, offer, libraries, _, original, identity = enrolled("weak")
        from anchor_exposure import bind

        bind(original, packet)
        detector = selected["detector_recipe_sha256"]
        staged.bind_native(packet, request["session"], request["inventory"], detector[7:], expected=selected["native_sha256"])
        request = dict(request, archive={"root": str(archive)}, libraries=libraries,
                       offer_sha256={ORDER[1]: identity["offer_sha256"]}, receiver="first-member-unrefined-short-scout")
        identity = dict(identity, native_sha256=selected["native_sha256"], detector=detector,
                        route=selected["choice"]["route"], selected=selected["selected"])
        publish_saved(request, root/mode, offer, path, packet, selected,
                      started=began, runtime=runtime, receipt_name=PUBLICATION)
    write(root/f"{mode}-execution.json", dict(identity=identity, orbit=orbit, rank=rank, rank_status=rank_status(True, rank)))


def launch(root):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    machine = host()
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Survey and solver outcomes require a frozen clean implementation")
    tmpfs(root.parent)
    root.mkdir()
    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    python = RELEASE/"venv/bin/python"
    child = [python, "-IB", Path(__file__)]
    write(root/"binding.json", dict(host=machine, order=MODES,
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    steps = [("prepare", [*child, "prepare", root]),
             ("fonts", [python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"])]
    steps.extend((mode, ["/usr/bin/timeout", "--kill-after=2s", "35s", *child, "worker", root, mode]) for mode in MODES)
    for label, args in steps:
        timing = measure(args, env, root/label)
        write(root/f"{label}-clock.json", timing)
        if timing["exit_code"]:
            raise RuntimeError(timing["stderr_tail"])


def seal(root):
    from empty_bootstrap import checked
    from leo.contracts.algo08_region import Algo08Region
    from preloaded_saved_score import science
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    outcomes = {}
    for mode in MODES:
        clock = read(root/f"{mode}-clock.json")
        selected = read(root/f"{mode}-selection.json")
        execution = read(root/f"{mode}-execution.json")
        target = root/mode
        publication = read(target/PUBLICATION)
        identity, receipt = execution["identity"], publication["receipt"]
        verified = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
        checked(native_file(target), selected["native_sha256"][7:])
        if (clock["exit_code"] or publication["waveform_calls"] or publication["handoffs"] != 1
                or not publication["staged_inventory"] or publication["native_sha256"] != identity["native_sha256"]
                or receipt["region"] != Algo08Region.parse(identity["original_offer"]).document()
                or verified["raw_authority"] != identity["authority"]):
            raise ValueError("Saved solve changed original authority or did not finish")
        detail = science(target, receipt, clock, identity) if receipt["decision"] == "complete" else None
        trace = read(target/"joint-research-receipt.json")
        outcomes[mode] = dict(clock=clock, selection=selected, publication=publication, execution=execution,
                              verified=verified, science=detail, early=trace["early_regional"])
    first, second = (outcomes[k]["execution"]["identity"] for k in MODES)
    if any(first[k] != second[k] for k in ("session", "inventory", "issued", "authority", "archive", "offer_sha256", "cutoff_utc_ns")):
        raise ValueError("The calibration pair does not share identical controlled inputs")
    write(root/"seal.json", outcomes)


def score(root):
    from eight_ms_held_score import geographic_reference, owner_differences
    from eight_ms_native_score import outcome

    pair = read(root/"seal.json")
    truth, pin = geographic_reference("weak")
    result = {mode: outcome(row["verified"]["arms"], row["publication"]["receipt"]["region"], truth)
              for mode, row in pair.items()}
    owners = None
    if all(row["science"] is not None for row in pair.values()):
        owners = {arm: owner_differences(*(pair[mode]["science"]["roles"][arm] for mode in MODES)) for arm in ARMS}
    write(root/"score.json", dict(arms=result, owners=owners, truth_source_sha256=pin,
          decisions={mode: row["publication"]["receipt"]["decision"] for mode, row in pair.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "prepare", "worker", "seal", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("mode", nargs="?", choices=MODES)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.root, args.mode)
    else:
        if args.action == "prepare":
            from empty_bootstrap import load_runtime

            load_runtime()
        {"launch": launch, "prepare": prepare, "seal": seal, "score": score}[args.action](args.root)
