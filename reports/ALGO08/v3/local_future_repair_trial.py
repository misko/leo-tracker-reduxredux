"""Publish the fixed-owner local continuation repair using the original saved short packets."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from types import SimpleNamespace

from aperture_trial import RELEASE, read, write
from dense_full_short_raw import usage
from dense_geographic_trial import host
from full_short_physical import environment
from local_future_inputs import future_observations
from north_factor_swap import continued
from short_stereo_trial import CASES, CONTROLS, HERE, controls, load_source, single_packet


def observe(donor, forward, prepare, native, *args, **kwargs):
    from leo.contracts.digests import canonical_digest

    if canonical_digest(native) != donor:
        raise ValueError("The local selector received the wrong authenticated short packet")
    return prepare(forward, *args, **kwargs)


def worker(saved, digest, output, recording, archive, region, geo, regional):
    from full_short_run import geographic_projection
    from joint_publication import run
    from local_future_repair import attach

    from leo.contracts.digests import canonical_digest

    started, wall = process_time(), perf_counter()
    native = read(saved)
    if canonical_digest(native) != digest:
        raise ValueError("The frozen signed source packet changed")
    forward = continued(native)
    future = future_observations(native, forward)
    selection = dict(cpu_s=process_time()-started, elapsed_s=perf_counter()-wall)
    options = SimpleNamespace(saved=saved, saved_digest=digest, output=output, recording=recording,
                              archive=archive, region=region, verify_images=True, optimized_full_catalogue=True)

    def repair(prepared, signed, measured):
        return attach(prepared, signed, measured, future)

    run(options, early_regional=True, keep_selected_rows=True,
        saved_receiver=native["provenance"]["detector_sha256"][7:],
        geographic_projector=lambda: geographic_projection(geo, regional),
        reuse_cold_rows=True, reuse_grid_phase_states=True, postfit_repair=repair,
        prepare_native_projection=partial(observe, digest, forward))
    files = (Path(__file__), HERE / "local_future_inputs.py", HERE / "local_future_repair.py",
             HERE / "local-future-repair-protocol.md", HERE / "joint_publication.py", HERE / "blind_joint_route.py")
    write(output / "local-future-policy.json", dict(native_sha256=digest, forward_sha256=canonical_digest(forward),
          future_ids=[row["observation_id"] for row in future], selection=selection,
          implementation={p.name: sha256(p.read_bytes()).hexdigest() for p in files}))


def replay(root, geo, regional, case):
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA

    machine = host()
    for library, pin in ((geo, GEOGRAPHIC_SHA), (regional, TRACK_SCORES_SHA)):
        if sha256(library.read_bytes()).hexdigest() != pin:
            raise ValueError("Unexpected reviewed research library")
    root.mkdir(exist_ok=True)
    env = environment(root)
    recording, archive, region, pin, offer, _ = load_source(case)
    from short_stereo_trial import source_for

    saved = source_for(case)[3]
    command = [RELEASE / "venv/bin/python", "-BPs", __file__, "worker", saved, pin,
               root / case, recording, archive["root"], region, geo, regional]
    before, started = usage(), perf_counter()
    process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
    elapsed = perf_counter()-started
    after = usage()
    write(root / f"{case}-clock.json", dict(machine=machine, source=pin, offer=offer, archive=archive,
          process=dict(elapsed_s=elapsed, status=process.returncode, **{k: after[k]-before[k] for k in before})))
    (root / f"{case}-stderr").write_text(process.stderr)
    if process.returncode:
        raise ValueError(process.stderr[-4000:])


def score(root, oracle):
    from aperture_score import PHYSICAL, references
    from joint_publication import artifacts
    from local_future_repair_oracle import FORWARD, NORTH_FORWARD
    from mixture_score import section

    from leo.contracts.digests import canonical_digest

    host()
    earlier = read(HERE / "measurements/bidirectional-selection.json")
    references_by_case = references()
    (physical,) = [r["reference"] for r in read(PHYSICAL)["cases"]
                   if r["dataset_label"] == "DS30-0016" and r["authority_eligible"]]
    truth = {"physical": [physical["latitude_deg"], physical["longitude_deg"]],
             **{case: references_by_case[f"{site}-containing"] for case, site in (("north", "north"), ("south-inside", "south"))}}
    expected = {name: read(HERE / "measurements" / name) for name in CONTROLS}
    archived = read(oracle)["results"]
    results = {}
    for case in CASES:
        folder = root / case
        _, _, _, digest, offer, native = load_source(case)
        trial = read(folder / "joint-research-receipt.json")
        receipt = trial["receipt"]
        policy = read(folder / "local-future-policy.json")
        terminal = read(folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
        clock = read(root / f"{case}-clock.json")
        notes = trial["route_details"]["local_future_repair"]
        stock_dir, stock_pin, stock_terminal_pin, _, forward_score = controls(case, expected)
        stock_terminal_path, = stock_dir.glob("fast-scan-automatic-work/*/terminal.json")
        stock = read(stock_terminal_path)
        origin = NORTH_FORWARD if case == "north" else FORWARD / case
        prior = read(origin / "joint-research-receipt.json")
        if (not trial["solve"]["grid_complete"] or policy["native_sha256"] != digest or clock["source"] != digest
                or canonical_digest(read(single_packet(folder))) != terminal["native_sha256"] or terminal["native_sha256"] != digest
                or canonical_digest(stock) != stock_terminal_pin or stock["native_sha256"] != stock_pin
                or canonical_digest(terminal) != receipt["terminal_sha256"] or not terminal["region"] == offer == stock["region"]
                or archived[case]["source"] != digest or archived[case]["forward"] != prior["receipt"]["terminal_sha256"]
                or json.loads(json.dumps(artifacts(folder, receipt))) != trial["evidence"]):
            raise ValueError("The local publication did not preserve its authenticated source, grid, and offer")
        future = {row["observation_id"] for row in future_observations(native, continued(native))}
        if future != set(policy["future_ids"]):
            raise ValueError("The application did not bind the measured future-supported roster")
        changes = {}
        for arm, selected in trial["selected_rows"].items():
            before = {o: (s, r) for o, s, r in prior["selected_rows"][arm]}
            after = {o: (s, r) for o, s, r in selected}
            additions = after.keys() - before.keys()
            eligible = {row["observation_id"]: (row["norad"], row["role"]) for row in notes.get("added", [])}
            if (not before.items() <= after.items() or not additions <= future
                    or notes["decision"] == "accepted" and eligible != {o: after[o] for o in additions}
                    or notes["decision"] != "accepted" and additions):
                raise ValueError("A reported add-on altered a prior owner or role")
            oracle_matches = sum(row["observation_id"] in additions and after[row["observation_id"]] == (row["norad"], row["role"])
                                 for row in archived[case]["changes"][arm]["additions"])
            changes[arm] = dict(before=len(before), after=len(after), added=len(additions), recovered_two_sided=oracle_matches)
        candidate = section(terminal["arms"], truth[case], stock["arms"])
        results[case] = dict(receipt=receipt, policy=policy, clock=clock, solve=trial["solve"], evidence=trial["evidence"],
                             repair=notes, changes=changes, score=candidate, forward=forward_score["score"],
                             two_sided=earlier[case]["score"], stock=section(stock["arms"], truth[case], stock["arms"]),
                             passes=all(v["delta_error_km"] <= .25 for v in candidate["arms"].values()),
                             forward_decision_clocks={k: trial["route_details"][k] for k in ("candidate_pre_evidence_clocks",
                                                      "signed_total_clocks", "exterior_clocks", "standard_evidence_clocks")})
    return dict(results=results, oracle_sha256=sha256(oracle.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode, names in (("run", ("root", "geo", "regional", "case")), ("score", ("root", "oracle", "output")),
                        ("worker", ("saved", "digest", "output", "recording", "archive", "region", "geo", "regional"))):
        command = sub.add_parser(mode)
        for name in names:
            if name == "case":
                command.add_argument(name, choices=CASES)
            else:
                command.add_argument(name, type=str if name == "digest" else Path)
    args = vars(parser.parse_args())
    mode = args.pop("mode")
    if mode == "run":
        replay(**args)
    elif mode == "worker":
        worker(**args)
    else:
        write(args["output"], score(args["root"], args["oracle"]))
