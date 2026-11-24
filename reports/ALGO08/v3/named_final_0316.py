"""Measure the current guarded final fit on the complete named DS30-0316 packet."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from empty_bootstrap import RELEASE, checked
from named_final_0374 import SOURCES
from named_wide_likelihood_trial import PINS, STAGE, enrollment
from prospective_0316_solver import LIBRARIES, worker
from raw_0016_best_trial import PROJECTION, PROJECTION_SHA


BASE = "250c07d0c86eed9c227003bb9e151726de7dee72"
PROTOCOL_SHA = "ffe67d7d7768bfd0e219f7e5d3272abcd3c87cf2bf1578f06bb9693f57a96e0a"
FROZEN_SOURCES = (*SOURCES, "provisional_salvage.py", "fragment_gate_cross.py", "short_graph_guard.py",
                  "grid_feature_projection.py", "grid_feature_projection.c", "verified_png_reads.py", "empty_family_calibration.py")
HISTORICAL = Path("/dev/shm/leo-v3-named-wide-0316-run02")
HISTORICAL_ADMISSION = "6006c654f8f232947ed2a03d767f1bbf5a7b4acd4a5d901850a118ef7af42609"
HISTORICAL_CLOCK = "d7eb299bd26d42b5a9262dd0e7d83b2220c061d5632585e22a5fd77ed92350af"
HISTORICAL_SCORE = Path("/dev/shm/leo-v3-named-wide-0316-scored01.json")
HISTORICAL_SCORE_SHA = "c8f3ffea8849ae5d411f0122e2b2ac0a81c05c4e5352add742a9db8889ce3fc1"
PREPARATION_FAILURE = Path("/dev/shm/leo-v3-final-0316-transfer-result01/candidate-clock.json")
PREPARATION_FAILURE_SHA = "9c788e9946a63231ed4b42c323341219066aaaed84f3a6f5df31eea0bdc28ea3"
OPTIONS = dict(named_survivor_finish=True, withhold_empty_family_calibration=True, direct_residual_figures=True,
               direct_orbit_figures=True, reuse_verified_png_reads=True, grid_feature_projection_library=PROJECTION)


def digest(data):
    return sha256(data).hexdigest()


def frozen_sources():
    repo = HERE.parents[2]
    result = {}
    for name in FROZEN_SOURCES:
        path = HERE/name
        data = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", repo, "show", f"{BASE}:{path.relative_to(repo)}"])
        result[name] = digest(data)
        checked(path, result[name])
    return result


def configure(args, options=OPTIONS):
    for key, value in options.items():
        setattr(args, key, value)


def manifest_files(directory_pairs, inventory):
    signed = [[row["path"], row["manifest_digest"]] for row in inventory["segments"]]
    if signed != directory_pairs:
        raise ValueError("The archived manifest roster disagrees with the authenticated saved inventory")
    return [[str(Path(path)/"manifest.json"), pin] for path, pin in signed]


def run_worker(job, target):
    from aperture_trial import read, write
    import unified_short_bootstrap as entry

    original = entry.publish_active
    observed, png = {}, {}

    def active(args, *values, **kwargs):
        configure(args)
        receipt, result = original(args, *values, png_read_audit=png, **kwargs)
        observed.update(named_survivor_finish=result["named_survivor_finish"], png_readback=png,
                        grid_projection=result["grid_feature_projection"], empty_family_calibration=result["empty_family_calibration"])
        return receipt, result

    request = read(job)
    with patch.object(entry, "publish_active", active):
        worker(job, "cumulative", target, source_pins=request["source_pins"], inventory_file=Path(request["staged_inventory"]))
    write(target/"final-fit-options.json", observed)


def seal(root):
    paths = [path for path in root.rglob("*") if path.is_file() and path.name != "prediction-seal.json"
             and path.relative_to(root).parts[0] not in ("tmp", "fonts")]
    return {str(path.relative_to(root)): digest(path.read_bytes()) for path in sorted(paths)}


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs outputs and scratch")
    checked(HERE/"named-final-0316-protocol.md", PROTOCOL_SHA)
    request, archive, inventory = enrollment()
    request["manifests"] = manifest_files(request["manifests"], json.loads(checked(inventory, PINS["inventory"])))
    historical = json.loads(checked(HISTORICAL/"admission.json", HISTORICAL_ADMISSION))
    checked(HISTORICAL/"stock-clock.json", HISTORICAL_CLOCK)
    if historical["inputs"] != PINS or historical["archive"] != archive or historical["machine"] != machine:
        raise ValueError("Saved named comparator used different authenticated inputs or host settings")
    libraries = {name: pin for name, (_, pin) in LIBRARIES.items()}
    for name, pin in libraries.items():
        checked(Path(request["local_libraries"][name]), pin)
    checked(PROJECTION, PROJECTION_SHA)
    source = frozen_sources()
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root/name).mkdir()
    for font in (HISTORICAL/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/font.name).write_bytes(font.read_bytes())
    request.update(source_pins=source, staged_inventory=str(inventory),
                   options={key: str(value) if isinstance(value, Path) else value for key, value in OPTIONS.items()})
    job = root/"request.json"
    write(job, request)
    write(root/"admission.json", dict(base=BASE, case="DS30-0316", sources=source, machine=machine, protocol_sha256=PROTOCOL_SHA,
          libraries=libraries | {"grid_projection": PROJECTION_SHA}, historical_clock_sha256=HISTORICAL_CLOCK))
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    target = root/"candidate"
    argv = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", job, target]
    clock = measure(argv, env, target)
    write(root/"candidate-clock.json", dict(timing=clock, command=list(map(str, argv))))
    write(root/"prediction-seal.json", seal(root))
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])


def owner_evidence(named, archive, candidate):
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import ARMS, owner_delta

    changes = {}
    for arm in ARMS:
        stock = archive["selected_rows"].get(arm, [])
        research = candidate["selected_rows"].get(arm, [])
        if (canonical_digest(stock) != named["owners"][arm]["sha256"]
                or canonical_digest({oid: norad for oid, norad, _ in stock}) != named["science"]["owners"][arm]
                or research and canonical_digest({oid: norad for oid, norad, _ in research}) != candidate["science"]["owners"][arm]):
            raise ValueError("An ordered roster disagrees with its verified publication authority")
        changes[arm] = dict(all=owner_delta(stock, research),
                            predictive=owner_delta([row for row in stock if row[2] == "predictive"],
                                                   [row for row in research if row[2] == "predictive"]),
                            families=dict(named=len({row[1] for row in stock}), candidate=len({row[1] for row in research})))
    return changes


def score(root, output):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from local_future_cli_trial import native_packet
    from prospective_0316_solver import inspect
    from short_raw_diagnostic import pairs
    from triage_bounds import calibration_comparison

    witness = root/"prediction-seal.json"
    if read(witness) != seal(root):
        raise ValueError("The current candidate changed after sealing")
    admission, request, actual = (read(root/name) for name in ("admission.json", "request.json", "candidate-clock.json"))
    if actual["timing"]["exit_code"]:
        write(output, dict(admission=admission, process=actual, status="process_failed", pre_score_sha256=digest(witness.read_bytes())))
        return
    historical = json.loads(checked(HISTORICAL_SCORE, HISTORICAL_SCORE_SHA))
    earlier = json.loads(checked(STAGE/"result.json", PINS["reference"]))
    named = historical["runs"]["stock"]
    stock_archive = earlier["runs"]["stock"]
    comparator_clock = json.loads(checked(HISTORICAL/"stock-clock.json", HISTORICAL_CLOCK))
    comparator_path = HISTORICAL/"stock"
    stock_receipt = named["named"]["publication"]
    named_science = pairs.evidence(comparator_path, stock_receipt, comparator_clock["timing"]["started_unix_ns"], read_only=True)
    actual_named_figures = artifacts(comparator_path, stock_receipt)["images"]
    checked(native_packet(comparator_path), PINS["native"])
    if (admission["sources"] != frozen_sources() or historical["admission"]["inputs"] != PINS or not historical["equal_science_and_media"]
            or named["process"] != comparator_clock or named["named"]["acquisition"]["mode"] != "saved"
            or stock_receipt["terminal_sha256"] != stock_archive["worker"]["receipt"]["terminal_sha256"]
            or any(named_science[key] != named["science"][key] or named_science[key] != stock_archive["science"][key]
                   for key in ("arms", "owners", "scientific_digests", "raw_authority"))
            or json.loads(json.dumps(actual_named_figures)) != named["figures"]):
        raise ValueError("The named timing or its signed scientific and media comparator does not match")
    target = root/"candidate"
    trace = read(target/"saved-0316-worker.json")
    recorded = read(target/"final-fit-options.json")
    candidate = inspect(target, "cumulative", trace["receipt"], actual["timing"], request)
    independent = read(target/"joint-research-receipt.json")
    if not recorded["named_survivor_finish"]["requested"] or candidate["science"]["receipt"]["region"] != stock_receipt["region"] or not trace["graph"]["enabled"]:
        raise ValueError("The actual candidate did not use the current guarded composition and original region")
    owners = owner_evidence(named, stock_archive, candidate)
    geographic = calibration_comparison({"candidate": candidate["science"], "named": named_science,
                                         "earlier_cumulative": earlier["runs"]["cumulative"]["science"]}, "DS30-0316")
    comparisons = dict(owner_deltas=owners, same_grid_path=candidate["sidecars"] == stock_archive["sidecars"],
                       pngs_exact={key: json.loads(json.dumps(shape)) == named["figures"].get(key)
                                   for key, shape in candidate["figures"].items()})
    previous = earlier["runs"]["cumulative"]
    tiers = dict(candidate=dict(process=actual["timing"], solve=trace["solve"], layout=trace["layout"],
                               publication={key: independent[key] for key in ("publication_cpu_s", "publication_elapsed_s")}),
                 recent_named=dict(process=comparator_clock["timing"], trace=named["named"]),
                 earlier_cumulative=dict(process=previous["process"], solve=previous["worker"]["solve"]),
                 earlier_named=dict(process=stock_archive["process"], solve=stock_archive["worker"]["solve"]))
    write(output, dict(admission=admission, request=request, pre_score_sha256=digest(witness.read_bytes()),
                       historical_scored_sha256=HISTORICAL_SCORE_SHA, waveform_calls=0, candidate=candidate, known_named=named_science,
                       clocks=tiers, comparisons=comparisons, geographic=geographic, active_options=recorded,
                       failed_startup=json.loads(checked(PREPARATION_FAILURE, PREPARATION_FAILURE_SHA))["timing"],
                       fix_counts=dict(named=int(stock_receipt["decision"] == "complete"), candidate=int(trace["receipt"]["decision"] == "complete")),
                       stock_to_candidate_elapsed_ratio=comparator_clock["timing"]["elapsed_s"]/actual["timing"]["elapsed_s"],
                       stock_to_candidate_cpu_ratio=comparator_clock["timing"]["cpu_s"]/actual["timing"]["cpu_s"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="mode", required=True)
    for mode, fields in (("launch", ("root",)), ("worker", ("job", "target")), ("score", ("root", "output"))):
        sub = commands.add_parser(mode)
        for name in fields:
            sub.add_argument(name, type=Path)
    options = vars(cli.parse_args())
    action = options.pop("mode")
    {"worker": run_worker, "launch": launch, "score": score}[action](**options)
