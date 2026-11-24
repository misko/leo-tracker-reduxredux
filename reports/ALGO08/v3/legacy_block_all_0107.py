"""Time one unchanged all-member entry against the sealed ordinary tiny recording."""

import argparse
from pathlib import Path
import shutil
import sys

from legacy_block_0107_metadata import digest, checked, direct_tmpfs, metadata
from legacy_block_0107_score import read, snapshot, speedup_gate
from legacy_block_raw_0107 import HERE, checked_json, released_paths


WORK = Path("/dev/shm/leo-v3-legacy-all-0016")
FULL = Path("/dev/shm/leo-v3-legacy-all-0016-result02")
FULL_PIN = "9a13cc45e8933106a6be91c5ddfd575c87c311773499420131a094b44113b557"
TINY = Path("/dev/shm/leo-v3-legacy-block-0107-result01")
TINY_PIN = "f5c8b39c67f5ccc49f0ffa446d4144e62089ad7d8d20fe0459bc307b3d80ddae"


def move_arguments(positive, tiny, root, plan_pin):
    argv = list(positive)
    if Path(argv[5]) != WORK/"reports/ALGO08/v3/legacy_block_all_entry.py" or "--cairo-residual-layout" not in argv:
        raise ValueError("The measured full-map runtime or conservative scientific scope changed")
    for name in ("--recording", "--archive", "--region", "--archive-sha256"):
        argv[argv.index(name)+1] = tiny[tiny.index(name)+1]
    for name, value in (("--output", root/"indexed"), ("--legacy-map-custody", root/"maps/custody.json"),
                        ("--legacy-map-custody-sha256", plan_pin), ("--legacy-map-library", root/"maps/legacy-block.so")):
        argv[argv.index(name)+1] = str(value)
    return argv


def launch(root):
    boot = released_paths()
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from legacy_block_raw_0016 import seal
    from leo.contracts.digests import canonical_json_bytes
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    begin = boot.now()
    full = checked_json(FULL/"result.json", FULL_PIN)
    tiny = checked_json(TINY/"result.json", TINY_PIN)
    full_book = full["admission"]
    old = tiny["admission"]
    if (root.exists() or direct_tmpfs(root.parent) != Path("/dev/shm") or not full["qualified"] or not tiny["qualified"]
            or host() != full_book["machine"] or host() != old["machine"]):
        raise ValueError("The qualified positive/tiny controls and same host are mandatory")
    runtime = {path: val for path, val in full_book["sources"].items()
               if Path(path).name not in {"legacy_block_all_score.py", "legacy_block_raw_score.py"}}
    for name, pin in runtime.items():
        checked(direct_tmpfs(WORK/name), pin)
    frozen = old["metadata"]
    req = frozen["request"]
    recording = Path(req["recording"])
    verified_scope(Path(frozen["signed_stage"]), recording)
    paths = [staged_path(Path(row["path"]), root=recording) for row in frozen["files"].values()]
    resident(paths)
    # Metadata-only verification preserves the same causal and original scopes.
    stayed = metadata(WORK)
    if stayed["request"] != req or stayed["files"] != frozen["files"] or frozen["portable"] != stayed["portable"]:
        raise ValueError("The original tiny archive, exact extent or earlier index changed")
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(FULL/"fonts", root/"fonts")
    shared = boot.clock(begin)
    started_ready = boot.now()
    maps = root/"maps"
    maps.mkdir()
    plan = checked_json(TINY/"maps/custody.json", old["map_custody_sha256"])
    row, = plan["members"]
    if plan != old["plan"] or not row["map"]:
        raise ValueError("The completed earlier released verification has no authentic literal map")
    source = direct_tmpfs(TINY/"maps"/row["map"])
    checked(source, row["map_sha256"])
    (maps/row["map"]).hardlink_to(source)
    row["map_kind"] = "literal"
    binary = direct_tmpfs(FULL/"maps/legacy-block.so")
    binary_pin = full_book["preparation"]["build"]["binary_sha256"]
    checked(binary, binary_pin)
    (maps/"legacy-block.so").hardlink_to(binary)
    data = canonical_json_bytes(plan)
    (maps/"custody.json").write_bytes(data)
    plan_pin = "sha256:"+digest(data)
    command = move_arguments(full_book["commands"]["indexed"], old["commands"]["indexed"], root, plan_pin)
    ready = boot.clock(started_ready)
    write(root/"admission.json", dict(request=req, metadata=stayed, source_pins=runtime,
          full_result_sha256=FULL_PIN, tiny_result_sha256=TINY_PIN, original_map_sha256=row["map_sha256"],
          active_plan=plan, plan_pin=plan_pin, decoder_sha256=binary_pin, raw_preparation_bytes=0,
          prior_preparation=old["preparation"], shared_admission=shared, ready_checks=ready, command=command,
          protocol_sha256=digest((HERE/"legacy-block-all-0107-protocol.md").read_bytes())))
    try:
        measure_mode(root, "indexed", command, environment_for(root), lambda: resident(paths))
    finally:
        write(root/"prediction-seal.json", seal(root))


def reduce(full, tiny, book, indexed):
    result = {}
    positive = full["admission"]
    for metric in ("elapsed_s", "cpu_s"):
        old = full["prices"][metric]
        ordinary = {"DS30-0016": old["ordinary"], "DS30-0107": tiny["clocks"]["ordinary"][metric]}
        named = {"DS30-0016": tiny["cohort"][metric]["installed_historical"]["DS30-0016"],
                 "DS30-0107": tiny["admission"]["installed_prior"][metric]}
        children = {"DS30-0016": old["all_members"], "DS30-0107": indexed[metric]}
        ready = {"DS30-0016": children["DS30-0016"]+positive["ready_checks"][metric]
                 +positive["preparation"]["recovery_reuse"]["clock"][metric],
                 "DS30-0107": children["DS30-0107"]+book["ready_checks"][metric]}
        charged = {"DS30-0016": ready["DS30-0016"]+positive["shared_admission"][metric],
                   "DS30-0107": ready["DS30-0107"]+book["shared_admission"][metric]}
        first = {"DS30-0016": ready["DS30-0016"]+old["prior_complete_five_map_validation"]+old["measured_incremental_preparation"],
                 "DS30-0107": ready["DS30-0107"]+book["prior_preparation"]["clock"][metric]}
        result[metric] = dict(child=children, ready=ready, shared_charged=charged, map_first_use=first,
           ordinary_child_gate=speedup_gate(ordinary, children), ordinary_ready_gate=speedup_gate(ordinary, ready),
           historical_child_gate=speedup_gate(named, children), historical_ready_gate=speedup_gate(named, ready),
           historical_ready_and_common_gate=speedup_gate(named, charged), first_use_gate=speedup_gate(named, first),
           one_shared_producer=old["prior_portable_producer"], total_first_with_producer=sum(first.values())+old["prior_portable_producer"])
    return result


def score(root):
    sys.path.insert(0, str(HERE.parents[2]/"src"))
    released_paths()
    from aperture_trial import write
    from legacy_block_raw_0016 import seal

    full = checked_json(FULL/"result.json", FULL_PIN)
    tiny = checked_json(TINY/"result.json", TINY_PIN)
    book, run = (read(root/name) for name in ("admission.json", "indexed-clock.json"))
    if seal(root) != read(root/"prediction-seal.json") or run["command"] != book["command"] or (root/"ordinary").exists():
        raise ValueError("The sealed one-child all-member raw output changed")
    out = snapshot(root/"indexed", run["clock"], book["request"])
    before = tiny["paired"]["ordinary"]
    if any(out[key] != before[key] for key in ("native_digest", "terminal", "scan_digest", "graph_proof", "receiver_visits")):
        raise ValueError("The all-member generic entry changed the same signed withholding")
    audit = read(root/"indexed/legacy-map-acquisition.json")
    member, = audit["members"]
    signed, = book["active_plan"]["members"]
    if (member["kind"] != "map" or member["map_kind"] != "literal" or member["counts"] != dict(full=8, prefix=19, committed_bytes=24_960_000)
            or any(member[key] != value for key, value in signed.items()) or audit["binary_sha256"] != book["decoder_sha256"]
            or audit["custody_sha256"] != book["plan_pin"]):
        raise ValueError("The original signed map must be active on the exact full-map native runtime")
    write(root/"result.json", dict(qualified=True, admission=book, process=run["clock"], prior_ordinary=tiny["clocks"]["ordinary"],
          same_terminal=out, reader_audit=audit, cohort=reduce(full, tiny, book, run["clock"]),
          prediction_seal_sha256=digest((root/"prediction-seal.json").read_bytes())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    opt = parser.parse_args()
    {"launch": launch, "score": score}[opt.mode](opt.root)
