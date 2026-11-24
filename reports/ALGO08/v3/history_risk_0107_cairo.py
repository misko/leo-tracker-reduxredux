"""Measure one resident Cairo-enabled DS30-0107 candidate and close the raw pair cohort."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
from time import perf_counter

from . import history_risk_0107_raw as raw
from .history_risk_0016_cairo import candidate_argv, checked_json
from .history_risk_physical_cohort import BOUNDARIES, finite_positive


OLD_ROOT = Path("/dev/shm/leo-v3-history-risk-0107-raw01")
OLD_SCORE = OLD_ROOT.with_name("leo-v3-history-risk-0107-score01.json")
OLD_PIN = "19a54239fad54185b0cf18bbf5b75b4cb8981e3be101087ddb53005d5c5d40e3"
WEAK_SCORE = Path("/dev/shm/leo-v3-history-risk-0016-cairo-score01.json")
WEAK_PIN = "b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39"
CURRENT_SCORE_HELPER = {"reports/ALGO08/v3/history_risk_0016_raw.py":
                        "86f37791f478c0e3b858ccd798afa5ebf67d23cb50bc0bac4b4e70dbf3e231e4"}


def references():
    from exact_named_raw import staged_path
    from history_cairo_render import SOURCES
    from history_risk_0016_raw import bundle_sha, roster

    ordinary, weak = checked_json(OLD_SCORE, OLD_PIN), checked_json(WEAK_SCORE, WEAK_PIN)
    seal = staged_path(OLD_ROOT/"prediction-seal.json")
    if (not ordinary["qualified"] or ordinary["case"] != "DS30-0107" or not ordinary["same_opportunities"]
            or ordinary["admission"] != raw.read(OLD_ROOT/"admission.json") or raw.read(seal) != roster(OLD_ROOT)
            or ordinary["pre_score_sha256"] != sha256(seal.read_bytes()).hexdigest()
            or any(row["clock"]["exit_code"] for row in ordinary["measured_exits"].values())
            or not weak["qualified"] or not weak["checks"] or not all(weak["checks"].values())
            or weak["native"]["science"]["receipt"]["decision"] != "complete"
            or weak["named_children"] or weak["optional_process"]["clock"]["exit_code"] or weak["reused_stock"]["exit_code"]):
        raise ValueError("Require the sealed qualified DS30-0107 ordinary pair and actual DS30-0016 Cairo outcome")
    changes = weak["admission"]["adapters"] | weak["admission"]["renderer_sources"]
    if {f"reports/ALGO08/v3/{name}" for name in SOURCES} != set(weak["admission"]["renderer_sources"]):
        raise ValueError("The fixed Cairo source roster changed")
    sources = {f"reports/ALGO08/v3/{name}": pin for name, pin in ordinary["admission"]["sources"].items()}
    # The integrated helper fixes only how the earlier 0016 scorer reads a silent candidate.
    sources.update(changes | CURRENT_SCORE_HELPER)
    bundle_sha(raw.HERE.parents[2], sources)
    return ordinary, weak, sources


def launch(root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import write
    from continued_cfo_small_raw import RECORDING, input_inventory, residency
    from dense_geographic_trial import host
    from eight_ms_0107_pair import is_resident, verified_scope
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked
    from exact_named_raw import deny_backing, staged_path
    from guarded_cfo_small_raw import PRIOR
    from history_risk_0016_raw import roster
    from leo.operations.tle_archive import TleArchiveReader
    from north_direct_multichunk import checked_lease
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import pairs

    started = perf_counter()
    checked_lease()
    machine = host()
    if staged_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs output")
    staged = PRIOR/RECORDING.name
    verified_scope(staged, RECORDING)
    sys.addaudithook(deny_backing(RECORDING))
    reference, weak, sources = references()
    admitted = reference["admission"]
    req, original, _ = raw.controls()
    if (admitted["request"] != req or admitted["machine"] != machine or weak["admission"]["machine"] != machine
            or admitted["stage"] != str(staged)):
        raise ValueError("The local physical capture and shared benchmark environment must be the enrolled pair")
    session, members = input_inventory()
    if (session != req["session"] or any(dict(path=str(p), bytes=n, sha256=pin) != original["members"][key]
                                        for key, (p, n, pin) in members.items())
            or admitted["member_files"] != original["members"]):
        raise ValueError("The exact original 29-window physical inventory is required")

    offer, archive = staged_path(Path(req["region"])), staged_path(Path(req["archive"]["root"]))
    checked(offer, req["offer_sha256"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 51 or pairs.archive_identity(archive) != req["archive"]
            or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Expected the frozen local causal archive")
    paths = [staged_path(ref.path, root=archive) for ref in refs]
    resident_archive = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths]))["fincore"]
    if len(resident_archive) != len(refs) or any(row["res"] < row["size"] for row in resident_archive):
        raise ValueError("All original causal bodies must already be resident")
    if pairs.verified_v3(pairs.NAMED_V3) != admitted["stock"]:
        raise ValueError("The installed release must match the existing sealed denominator")
    for library in admitted["candidate_libraries"].values():
        checked(Path(library["path"]), library["sha256"])
    argv = candidate_argv(reference, root/"candidate")

    def resident():
        verified_scope(staged, RECORDING)
        caches = residency(members)
        if not is_resident(caches):
            raise ValueError("The original waveform and index must remain fully resident")
        return caches["payload"] | {"index_cache": caches["index"]}

    resident()
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(PRIOR/"fonts", root/"fonts")
    env = environment_for(root)
    help_text = subprocess.run([*argv[:6], "--help"], capture_output=True, check=True, timeout=10, env=env).stdout
    if b"--cairo-six-sheets" not in help_text:
        raise ValueError("The actual isolated raw CLI rejected the enrolled renderer opt-in")
    write(root/"admission.json", dict(request=req, machine=machine, command=argv, sources=sources,
          references={str(OLD_SCORE): OLD_PIN, str(WEAK_SCORE): WEAK_PIN}, stage=str(staged),
          files=original["members"], candidate_libraries=admitted["candidate_libraries"], named_children=0,
          catalogue=dict(snapshots=len(refs), bytes=sum(row["size"] for row in resident_archive)),
          setup_wall_s=perf_counter()-started, original_backing_bytes=0, conditioning_bytes=0))
    try:
        measure_mode(root, "candidate", argv, env, resident)
    finally:
        write(root/"prediction-seal.json", roster(root))


def same_withhold(current, reference):
    if (current["science"] != reference["science"] or current["digest"] != reference["digest"]
            or current["opportunities"] != reference["opportunities"] or current["excluded"] != reference["excluded"]
            or current["factors"] != reference["factors"] or current["factors"] != 19
            or current["figures"] or current["sidecars"] is not None or current["route"] is not None):
        raise ValueError("The Cairo-enabled candidate changed signed probes, exclusions, or the zero-product terminal")


def summarize(clocks):
    if set(clocks) != {"DS30-0107", "DS30-0016"}:
        raise ValueError("Use exactly the one fix and one withholding recording")
    timings = {}
    for metric in BOUNDARIES:
        if any(row[mode]["exit_code"] or not finite_positive(row[mode][metric])
               for row in clocks.values() for mode in ("candidate", "stock")):
            raise ValueError("Both comparisons require actual successful exits and positive paid clocks")
        ratios = {case: row["candidate"][metric]/row["stock"][metric] for case, row in clocks.items()}
        totals = {mode: sum(row[mode][metric] for row in clocks.values()) for mode in ("candidate", "stock")}
        timings[metric] = dict(paired_candidate_over_stock=ratios, totals=totals,
            median_ratio=median(ratios.values()), summed_ratio=totals["candidate"]/totals["stock"])
    wall = timings["elapsed_s"]
    gates = {name: dict(median=wall["median_ratio"] <= target, sum=wall["summed_ratio"] <= target,
                        both=max(wall["median_ratio"], wall["summed_ratio"]) <= target)
             for name, target in (("1.6x", .625), ("2x", .5))}
    return dict(timing=timings, gates=gates)


def score(root, destination):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import write
    from history_risk_0016_raw import roster

    reference, weak, sources = references()
    admission, measured = (raw.read(root/file) for file in ("admission.json", "candidate-clock.json"))
    seal = root/"prediction-seal.json"
    req, _, expected = raw.controls()
    if (raw.read(seal) != roster(root) or admission["request"] != req or admission["sources"] != sources
            or admission["named_children"] or (root/"stock").exists() or (root/"stock-clock.json").exists()
            or measured["command"] != admission["command"] or measured["command"] != candidate_argv(reference, root/"candidate")
            or any(cache["members"] != 1 or cache["unavailable"] or cache["cached_pages"] != cache["observed_file_pages"]
                   for phase in ("cache_before", "cache_after") for cache in (measured[phase], measured[phase]["index_cache"]))):
        raise ValueError("Unexpected measured command, custody, or publication state")
    current = raw.published(root, "candidate", measured, req, expected["candidate"])
    same_withhold(current, reference["runs"]["candidate"])
    stock = reference["runs"]["stock"]
    if (current["opportunities"] != stock["opportunities"] or current["excluded"] != stock["excluded"]
            or measured["clock"]["started_unix_ns"] <= stock["process"]["clock"]["started_unix_ns"]):
        raise ValueError("The candidate did not use the same signed opportunities after the original pair")
    clocks = {"DS30-0107": dict(candidate=measured["clock"], stock=stock["process"]["clock"]),
              "DS30-0016": dict(candidate=weak["optional_process"]["clock"], stock=weak["reused_stock"])}
    setups = {"DS30-0107": admission["setup_wall_s"], "DS30-0016": weak["admission"]["prepared_wall_s"]}
    charged = {case: dict(row, candidate=row["candidate"] | {"elapsed_s": row["candidate"]["elapsed_s"]+setups[case]})
               for case, row in clocks.items()}
    write(destination, dict(qualified=True, clocks=clocks, cohort=summarize(clocks),
          candidate_setup_charged=summarize(charged), setup_wall_s=setups, admission=admission,
          original_0107_setup_wall_s=reference["admission"]["setup_wall_s"],
          ordinary_candidate_clocks={"DS30-0107": reference["measured_exits"]["candidate"]["clock"],
                                     "DS30-0016": weak["measured_ordinary"]},
          decisions={"DS30-0107": "withheld", "DS30-0016": "complete"},
          optional_0107=current, verification_0016=weak["checks"],
          pre_score_sha256=sha256(seal.read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.output is None or args.output.resolve().is_relative_to(args.root.resolve()):
        parser.error("Supply an external score output")
    else:
        score(args.root, args.output)
