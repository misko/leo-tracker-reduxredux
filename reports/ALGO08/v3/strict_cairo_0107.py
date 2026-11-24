"""Extend the strict Cairo physical comparison with the tiny 29-visit withhold."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from reports.ALGO08.v3 import history_risk_0107_cairo as cairo
from reports.ALGO08.v3 import strict_cairo_0016 as weak
from reports.ALGO08.v3 import strict_packed_0107 as packed


CAIRO_ROOT = Path("/dev/shm/leo-v3-history-risk-0107-cairo-result01")
CAIRO_SCORE = Path("/dev/shm/leo-v3-history-risk-0107-cairo-score02.json")
CAIRO_PIN = "6f6923e6a4be803069581d5a254148c6e322d9e0c4ea4e93de1062dd2bb485e9"
PACKED_ROOT = Path("/dev/shm/leo-v3-strict-packed-0107-result02")
PACKED_SCORE = Path("/dev/shm/leo-v3-strict-packed-0107-score02.json")
PACKED_PIN = "b85ffda145784a610502b118b68b779ea2b806bd7d35919620a5c2f6296dbf91"
CONVERSION_PIN = "f0457bd6ad67e70edc4fda6cc5bd250b7f6e610c5633a953561c3de61e90144a"
WEAK_SCORE = Path("/dev/shm/leo-v3-strict-cairo-0016-score01.json")
WEAK_PIN = "cc2268406d1e6cc9c3d3a8aec364c92ef89783b1904ba61630d466f301591d6d"
SOURCES = (Path(__file__).name, "strict-cairo-0107-protocol.md", "history_risk_0107_raw.py", "history_risk_0107_cairo.py",
           "strict_packed_0107.py", *weak.SOURCES)
REVIEW_ONLY = {f"reports/ALGO08/v3/{name}" for name in ("history_risk_0016_raw.py", "history_risk_0107_raw.py")}


def sources():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def references():
    from empty_bootstrap import checked

    old = cairo.checked_json(cairo.OLD_SCORE, cairo.OLD_PIN)
    prior = cairo.checked_json(CAIRO_SCORE, CAIRO_PIN)
    verified = cairo.checked_json(PACKED_SCORE, PACKED_PIN)
    positive = cairo.checked_json(WEAK_SCORE, WEAK_PIN)
    req, original, _ = cairo.raw.controls()
    seal = CAIRO_ROOT/"prediction-seal.json"
    earlier_bootstrap = prior["optional_0107"]["bootstrap"]
    if (not old["qualified"] or not prior["qualified"] or not old["same_opportunities"]
            or not verified["pass_through"] or not all(verified["strict_checks"].values())
            or not positive["qualified"] or not all(positive["checks"].values()) or positive["admission"]["sources"] != weak.pins()
            or prior["admission"]["request"] != old["admission"]["request"] or prior["admission"]["request"] != req
            or prior["clocks"]["DS30-0107"]["stock"] != old["measured_exits"]["stock"]["clock"]
            or json.loads(checked(seal, prior["pre_score_sha256"])) != weak.original.roster(CAIRO_ROOT)
            or earlier_bootstrap != cairo.raw.read(CAIRO_ROOT/"candidate/unified-short-bootstrap.json")
            or earlier_bootstrap.get("packed_ci16_input") is not None
            or verified["plan"]["resumed_conversion_sha256"] != CONVERSION_PIN
            or verified["conversion"] != json.loads(checked(PACKED_ROOT/"conversion.json", CONVERSION_PIN))
            or verified["plan"]["original"]["recording"] != req["recording"]
            or verified["measured"]["native"]["candidate"]["source"]["raw_recording_authority_digest"] != req["authority"]):
        raise ValueError("Original raw, proven packed derivative and scored Cairo controls must all match")
    active = {name: pin for name, pin in prior["admission"]["sources"].items() if name not in REVIEW_ONLY}
    weak.original.bundle_sha(ROOT, active)
    return old, prior, verified, positive, req, original


def run(root):
    from aperture_trial import write
    from continued_cfo_small_raw import RECORDING, input_inventory, residency
    from dense_geographic_trial import host
    from eight_ms_0107_pair import is_resident, verified_scope
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked, clock, now
    from exact_named_raw import deny_backing, parser, staged_path
    from guarded_cfo_small_raw import PRIOR
    from leo.operations.tle_archive import TleArchiveReader
    from north_direct_multichunk import checked_lease
    from north_strict_read import resident_packed
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import pairs

    begin = now()
    checked_lease()
    machine = host()
    if root.exists() or staged_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs root for one candidate")
    staged = PRIOR/RECORDING.name
    verified_scope(staged, RECORDING)
    sys.addaudithook(deny_backing(RECORDING))
    old, earlier, verified, positive, req, original = references()
    session, members = input_inventory()
    if (session != req["session"] or any(dict(path=str(p), bytes=size, sha256=pin) != original["members"][name]
                                        for name, (p, size, pin) in members.items())
            or earlier["admission"]["stage"] != str(staged) or earlier["admission"]["files"] != original["members"]
            or any(machine != witness for witness in (earlier["admission"]["machine"], positive["admission"]["machine"], verified["plan"]["machine"]))
            or pairs.verified_v3(pairs.NAMED_V3) != old["admission"]["stock"]):
        raise ValueError("The original resident file, installed control or measurement platform changed")
    checked(staged_path(Path(req["region"])), req["offer_sha256"])
    archive = staged_path(Path(req["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 51 or pairs.archive_identity(archive) != req["archive"]
            or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Require exact original causal archive and pre-capture cutoff")
    paths = [staged_path(ref.path, root=archive) for ref in refs]
    archive_residency = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths]))["fincore"]
    if len(archive_residency) != len(refs) or any(item["res"] < item["size"] for item in archive_residency):
        raise ValueError("The entire causal archive must be resident")
    for asset in earlier["admission"]["candidate_libraries"].values():
        checked(Path(asset["path"]), asset["sha256"])

    def resident():
        verified_scope(staged, RECORDING)
        scopes = residency(members)
        if not is_resident(scopes):
            raise ValueError("The genuine original data and index must remain resident")
        return scopes["payload"] | {"index_cache": scopes["index"]}

    resident()
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(PRIOR/"fonts", root/"fonts")
    common = clock(begin)
    begin = now()
    clip = verified["plan"]["original"]
    if clip["manifests"] != [dict(path=str(members["manifest"][0]), digest=members["manifest"][2])]:
        raise ValueError("The paid conversion is from a different original manifest")
    config, folders, codec = packed.prepared_derivative(PACKED_ROOT, clip, CONVERSION_PIN)
    before = resident_packed(Path(config["map"]).parent, folders, codec)
    command = weak.quote(earlier["admission"]["command"], root/"candidate", config)
    actual = parser().parse_args(command[6:])
    if not (actual.strict_packed_eight and actual.history_risk_route and actual.cairo_six_sheets):
        raise ValueError("Use the same three explicit runtime options as the qualified positive")
    derivative_setup = clock(begin)
    write(root/"admission.json", dict(request=req, machine=machine, command=command, sources=sources(), named_children=0,
          resident_original=str(staged), original_files=original["members"], packed=config, before=before,
          references=dict(stock=cairo.OLD_PIN, cairo=CAIRO_PIN, qualified_conversion=PACKED_PIN, weak=WEAK_PIN),
          conversion_sha256=CONVERSION_PIN, setup=dict(common=common, derivative=derivative_setup)))
    try:
        measure_mode(root, "candidate", command, environment_for(root), resident, require_success=False)
    finally:
        write(root/"packed-after.json", resident_packed(Path(config["map"]).parent, folders, codec))
        write(root/"prediction-seal.json", seal_roster(root))


def seal_roster(root):
    return weak.original.roster(root) | {"packed-after.json": sha256((root/"packed-after.json").read_bytes()).hexdigest()}


def cohort(tiny, positive):
    def exposures(row):
        return {name: dict(stock=row["stock"], candidate=row["candidate"] | {"elapsed_s": wall, "cpu_s": cpu})
                for name, (wall, cpu) in row["scopes"].items()}

    tiny_scopes, positive_scopes = exposures(tiny), exposures(positive)
    if tiny_scopes.keys() != positive_scopes.keys():
        raise ValueError("Compare only the same paid scope")
    return {name: cairo.summarize({"DS30-0107": small, "DS30-0016": positive_scopes[name]}) for name, small in tiny_scopes.items()}


def expenses(candidate, stock, common, setup, conversion):
    child = candidate["elapsed_s"], candidate["cpu_s"]
    ready = child[0]+setup["elapsed_s"], child[1]+setup["cpu_s"]
    total = conversion["total_including_compiler_and_verification"]
    migration = total["wall_ns"]/1e9, total["cpu_ns"]/1e9+conversion["compiler"]["compiler_cpu_s"]
    first = ready[0]+migration[0], ready[1]+migration[1]
    return dict(candidate=candidate, stock=stock, scopes=dict(child=child, ready=ready, first=first,
                ready_with_common=(ready[0]+common["elapsed_s"], ready[1]+common["cpu_s"]),
                first_with_common=(first[0]+common["elapsed_s"], first[1]+common["cpu_s"])))


def score(root, output):
    from aperture_trial import write
    from empty_bootstrap import checked
    from local_future_cli_trial import native_packet
    from packed_combined_input import VARIABLE_EIGHT_SCHEMA
    from strict_history_raw_trial import packed_integrity

    ordinary, earlier, verified, positive, req, _ = references()
    admission, log, after, seal = (cairo.raw.read(root/name) for name in
                                 ("admission.json", "candidate-clock.json", "packed-after.json", "prediction-seal.json"))
    conversion = verified["conversion"]
    config = conversion["request"]
    if (seal != seal_roster(root) or admission["sources"] != sources() or admission["request"] != req
            or admission["packed"] != config or admission["conversion_sha256"] != CONVERSION_PIN or admission["named_children"]
            or log["command"] != weak.quote(earlier["admission"]["command"], root/"candidate", config)
            or log["command"] != admission["command"] or (root/"stock").exists() or (root/"stock-clock.json").exists()):
        raise ValueError("The one executed candidate must match the qualified packed derivative and timed command")
    if log["clock"]["exit_code"]:
        write(output, dict(qualified=False, admission=admission, candidate=log))
        return
    _, _, expected = cairo.raw.controls()
    current = cairo.raw.published(root, "candidate", log, req, expected["candidate"], strict_map_sha256=config["map_sha256"])
    cairo.same_withhold(current, earlier["optional_0107"])
    stock = ordinary["runs"]["stock"]
    scan = cairo.verify_scans(root, current, ordinary["runs"]["candidate"], stock)
    build, = conversion["sections"]
    index = Path(config["map"]).parent/build["binding"]["directory"]/"source-index.jsonl"
    rows = [json.loads(line) for line in checked(index, build["original"]["index_sha256"][7:]).splitlines()]
    native = cairo.raw.read(native_packet(root/"candidate"))
    schedule = packed.signed_schedule(native["source"]["probes"], rows)
    audit = current["bootstrap"]["packed_ci16_input"]
    acquire = packed_integrity(audit, conversion)
    if (not packed.complete_reader(audit, build, schedule) or audit["schema"] != VARIABLE_EIGHT_SCHEMA
            or audit["members"][0]["empty_parts"] != 2 or len(schedule) != 27
            or schedule != verified["expected_apertures"] or current["opportunities"] != stock["opportunities"]
            or current["excluded"] != stock["excluded"] or after["cached_pages"] != admission["before"]["cached_pages"]
            or acquire["apertures"] != current["bootstrap"]["receiver_audit"]["native"]["visits"]):
        raise ValueError("The strict receiver did not authenticate and replay the exact original schedule")
    overtime = expenses(log["clock"], stock["process"]["clock"], admission["setup"]["common"], admission["setup"]["derivative"], conversion)
    psetup = positive["admission"]["phase_setup"]
    weak_time = expenses(positive["candidate"], positive["stock"], psetup["common"], psetup["candidate_specific"], positive["conversion"])
    write(output, dict(qualified=True, case="DS30-0107", admission=admission, candidate=current, acquire=acquire,
          conversion=conversion, scan=scan, costs=overtime, positive_costs=weak_time, cohort=cohort(overtime, weak_time),
          original_cairo=earlier["clocks"]["DS30-0107"]["candidate"], named_children=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    else:
        score(args.root, args.output or args.root/"result.json")
