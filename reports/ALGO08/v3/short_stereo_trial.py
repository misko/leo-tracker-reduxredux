"""Run and independently score the three frozen saved short stereo selections."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time_ns
from types import SimpleNamespace

from aperture_trial import RELEASE, archive_identity, read, write
from dense_full_short_raw import usage
from dense_geographic_trial import host
from full_short_graph_transfer import HERE, PHYSICAL, inputs
from full_short_physical import environment
from full_short_south import INSIDE, checked
from north_combined import assignments
from north_factor_swap import PINS
from short_stereo_evidence import filtered


CASES = ("physical", "north", "south-inside")
NORTH_ROOT = Path("/var/tmp/leo-north-short-regional-nov23")
SOUTH_PAIR_SHA = "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0"
CONTROLS = ("north-combined.json", "north-causal-transfer.json", "causal-selection-transfer.json", "weak-combined-raw.json")


def single_packet(directory):
    path, = directory.glob("fast-scan-automatic-work/*/detections.json")
    return path


def source_for(case):
    if case == "north":
        pair, _ = assignments()
        return (Path(pair["recording"]), pair["archive"], Path(pair["region"]), single_packet(NORTH_ROOT / "containing"),
                PINS["containing"], pair["runs"]["candidate"]["receipt"]["region"])
    return inputs(case)


def load_source(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    recording, archive, region, path, pin, offer = source_for(case)
    native = read(path)
    if (canonical_digest(native) != pin or archive_identity(Path(archive["root"])) != archive
            or Algo08Region.parse(read(region)).document() != offer):
        raise ValueError("Saved packet, causal archive or frozen containing offer changed")
    return recording, archive, region, pin, offer, native


def replay(root, geo, regional):
    from leo.contracts.digests import canonical_digest
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA

    settings = host()
    for library, pin in ((geo, GEOGRAPHIC_SHA), (regional, TRACK_SCORES_SHA)):
        if sha256(library.read_bytes()).hexdigest() != pin:
            raise ValueError("Expected the reviewed regional and geographic builds")
    root.mkdir(exist_ok=False)
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    write(root / "binding.json", dict(cases=CASES, host=settings, geographic_sha256=GEOGRAPHIC_SHA,
              regional_sha256=TRACK_SCORES_SHA, saved=True, track_graph="installed", early_regional=True,
              optimized_full_catalogue=True, reuse_cold_track_rows=True, reuse_grid_phase_states=True,
              verify_images=True))
    for case in CASES:
        recording, archive, region, pin, offer, native = load_source(case)
        start = process_time_ns()
        packet, evidence, recipe = filtered(native)
        detector_cpu = (process_time_ns()-start)/1e9
        packet_path = root / f"{case}-input.json"
        write(packet_path, packet)
        write(root / f"{case}-selection.json", dict(source_pin=pin, target_pin=canonical_digest(packet),
              recipe=recipe, recording=str(recording), archive=archive, offer=offer, filter_cpu_s=detector_cpu,
              visits=evidence))
        command = [python, "-BPs", __file__, "worker", packet_path, canonical_digest(packet),
                   packet["provenance"]["detector_sha256"][7:], root / case, recording, archive["root"], region, geo, regional]
        before, start = usage(), perf_counter()
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
        after = usage()
        write(root / f"{case}-process.json", dict(elapsed_s=perf_counter()-start, status=proc.returncode,
             **{key: after[key]-before[key] for key in before}))
        (root / f"{case}-stderr").write_text(proc.stderr)
        if proc.returncode:
            raise ValueError(proc.stderr[-4000:])


def worker(saved, digest, pin, output, recording, archive, region, geo, regional):
    from full_short_run import geographic_projection
    from joint_publication import run

    options = SimpleNamespace(saved=saved, saved_digest=digest, output=output, recording=recording, archive=archive,
                              region=region, verify_images=True, optimized_full_catalogue=True)
    run(options, early_regional=True, keep_selected_rows=True, saved_receiver=pin,
        geographic_projector=lambda: geographic_projection(geo, regional),
        reuse_cold_rows=True, reuse_grid_phase_states=True)


def controls(case, reference):
    saved, north_causal, transfer, physical = (reference[name] for name in CONTROLS)
    if case == "north":
        record = saved["cases"]["stock"]
        return NORTH_ROOT / "stock", record["native_sha256"], record["terminal_sha256"], saved["cases"]["containing"]["score"], north_causal["cases"]["containing"]["score"]
    if case == "physical":
        record = physical["runs"]["stock"]
        return PHYSICAL / "stock", record["native_sha256"], record["terminal_sha256"], transfer[case]["unfiltered"], transfer[case]["score"]
    record = checked(INSIDE, SOUTH_PAIR_SHA)["runs"]["candidate"]
    return INSIDE.parent / "candidate", "sha256:26e4ce9c24e81761e4d92cf05e29474e4ced9ba4effdffff89b817c0ea9f9ce3", record["receipt"]["terminal_sha256"], transfer[case]["unfiltered"], transfer[case]["score"]


def score_counts(stock, native, evidence, rows):
    from short_primary_epoch_audit import paired_probes

    probes = paired_probes(stock, native)
    lane_audit = {(visit["visit"], lane["receiver"]): lane for visit in evidence for lane in visit["lanes"]}
    keys, stats, rescue_details = {}, Counter(), []
    for oid, probe, before, short, _ in probes:
        entry = lane_audit[(probe["visit_index"], probe["receiver_id"])]
        if bool(short) != entry["had_factor"] or (entry["rescued"] and entry["continued"]):
            raise ValueError("Filter audit does not bind the original opportunity")
        if not short:
            continue
        presence = "stock_present" if before else "stock_empty"
        status = "continued" if entry["continued"] else "rescued" if entry["rescued"] else "dropped"
        keys[oid] = status, presence
        stats[(status, presence)] += 1
        if status == "rescued":
            rescue_details.append(dict(observation_id=oid, visit=probe["visit_index"], receiver=probe["receiver_id"],
                                       channel=probe["channel"], stock_present=bool(before), history_votes=entry["votes"]))
    owner_status = {}
    for arm, items in rows.items():
        if len({oid for oid, _, _ in items}) != len(items):
            raise ValueError("The public owner map duplicated an observation")
        status = Counter(keys[oid] for oid, _, _ in items)
        if any(k[0] == "dropped" for k in status):
            raise ValueError("The public owner map contains a dropped observation")
        owner_status[arm] = {f"{k[0]}_{k[1]}": n for k, n in sorted(status.items())}
    stereo = Counter(v["stereo_mode"] for v in evidence if v["stereo_mode"] is not None)
    for v in evidence:
        stats["visits", "two_factors"] += all(a["had_factor"] for a in v["lanes"])
        stats["visits", "timing_coincident"] += v["timing_match"]
        stats["visits", "prior_offset_available"] += v["prior_offset_hz"] is not None
    return dict(counts={f"{k[0]}_{k[1]}": n for k, n in sorted(stats.items())}, accepted_stereo=dict(stereo),
                rescued=rescue_details, owners=owner_status)


def score(root):
    from aperture_score import PHYSICAL as PHYSICAL_REFERENCE, references
    from joint_publication import artifacts
    from mixture_score import section
    from north_interlaced_raw import NORTH, TRUTH_SHA, verified

    from leo.contracts.digests import canonical_digest

    host()
    (physical,) = [row["reference"] for row in read(PHYSICAL_REFERENCE)["cases"]
                   if row["dataset_label"] == "DS30-0016" and row["authority_eligible"]]
    north_key = json.loads(verified(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (north,) = {tuple(v["truth"]) for v in north_key["answers"].values() if v["recording"] == NORTH}
    truth = {"physical": [physical["latitude_deg"], physical["longitude_deg"]], "north": north,
             "south-inside": references()["south-containing"]}
    control_paths = tuple(HERE / "measurements" / name for name in CONTROLS)
    reference = {path.name: read(path) for path in control_paths}
    results = {}
    for case in CASES:
        _, _, _, original, offer, native = load_source(case)
        folder = root / case
        report = read(folder / "joint-research-receipt.json")
        receipt = report["receipt"]
        published = single_packet(folder)
        packet, audit, recipe = filtered(native)
        seal = read(root / f"{case}-selection.json")
        terminal = read(folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
        stock_dir, stock_pin, stock_terminal_pin, unfiltered, causal = controls(case, reference)
        stock_path = single_packet(stock_dir)
        stock_terminal_path, = stock_dir.glob("fast-scan-automatic-work/*/terminal.json")
        stock, stock_terminal = read(stock_path), read(stock_terminal_path)
        output_pin = canonical_digest(packet)
        if not (canonical_digest(stock) == stock_pin == stock_terminal["native_sha256"]
                and canonical_digest(stock_terminal) == stock_terminal_pin
                and terminal["region"] == receipt["region"] == stock_terminal["region"] == offer
                and canonical_digest(terminal) == receipt["terminal_sha256"]
                and canonical_digest(read(published)) == terminal["native_sha256"] == report["saved_digest"] == output_pin
                and seal["source_pin"] == original and seal["target_pin"] == output_pin and seal["visits"] == audit
                and seal["recipe"] == recipe and json.loads(json.dumps(artifacts(folder, receipt))) == report["evidence"]):
            raise ValueError("The study failed to bind the original input, recipe, offer or publication")
        science = section(terminal["arms"], truth[case], stock_terminal["arms"])
        results[case] = dict(source_sha256=original, filtered_sha256=output_pin, stock_sha256=stock_pin,
                             stock_terminal_sha256=stock_terminal_pin, recipe=recipe, terminal_sha256=receipt["terminal_sha256"],
                             offer=offer, candidate_decision=receipt["decision"],
                             passes=receipt["decision"] == "complete" and len(science["arms"]) == 2
                                    and all(a["delta_error_km"] <= .25 for a in science["arms"].values()),
                             route=report["route"], solve=report["solve"], selected_counts={k: len(v) for k, v in report["selected_rows"].items()},
                             process=read(root / f"{case}-process.json"), filter_cpu_s=seal["filter_cpu_s"],
                             proof=report["early_regional"], evidence=report["evidence"], score=science,
                             stock=section(stock_terminal["arms"], truth[case], stock_terminal["arms"]),
                             unfiltered=unfiltered, causal=causal, audit=score_counts(stock, native, audit, report["selected_rows"]))
    source = (*control_paths, Path(__file__), HERE / "short-stereo-evidence-protocol.md", HERE / "short_stereo_evidence.py")
    return dict(binding=read(root / "binding.json"), source_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in source},
                results=results)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="mode", required=True)
    for mode, names in (("run", ("root", "geo", "regional")), ("score", ("root", "output")),
                        ("worker", ("saved", "digest", "pin", "output", "recording", "archive", "region", "geo", "regional"))):
        parser = subs.add_parser(mode)
        for name in names:
            parser.add_argument(name, type=str if name in ("digest", "pin") else Path)
    arguments = vars(cli.parse_args())
    mode = arguments.pop("mode")
    if mode == "run":
        replay(**arguments)
    elif mode == "worker":
        worker(**arguments)
    else:
        write(arguments["output"], score(arguments["root"]))
