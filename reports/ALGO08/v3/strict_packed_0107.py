"""Compare strict packed 20/8 and installed v3 on the full staged physical DS30-0107."""

import argparse
from collections import Counter
from functools import partial
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from . import adaptive_raw_trial as adaptive
from . import adaptive_withhold_0107 as withhold
from . import eight_ms_0107_pair as paired
from . import north_strict_read as strict

from aperture_trial import read, write
from continued_cfo_small_raw import CASE, INPUTS, RECORDING, input_inventory, residency
from empty_bootstrap import checked
from guarded_cfo_small_raw import PRIOR


MERGED = "0285f1ec450fb6a1f19553205565ec0a3b5a7cc4"
EARLIER = ("adaptive-withhold-0107.json.gz", "b9788ba3d3c751d1dedb21033a9950be171616e7a551b69941a4cd5326b3ab57")
SOURCE = Path(__file__).name


def candidate_command(previous, recording, archive, offer, target, *, packed, reference):
    ordinary = paired.candidate_command(previous, recording, archive, offer, target)
    if adaptive.adaptive_command(ordinary, target) != paired.candidate_command(reference, recording, archive, offer, target):
        raise ValueError("Keep the exact accepted DS30-0107 lean command")
    return adaptive.adaptive_command(ordinary, target, strict=packed)


def run(root):
    from dense_geographic_trial import host
    from seekable_eight_raw import clocks, elapsed

    begin = clocks()
    machine = host()
    tree = paired.HERE.parents[2]
    git = ["git", "-c", f"safe.directory={tree}", "-C", str(tree)]
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    changed = subprocess.check_output([*git, "diff", "--name-only", MERGED, revision], text=True).splitlines()
    components = (SOURCE, "north_strict_read.py", "strict-packed-0107-protocol.md", "packed_combined_input.py",
                  "seekable_member.py", "measurements/strict-packed-0107-initial-admission.json")
    allowed = {f"reports/ALGO08/v3/{name}" for name in components}
    allowed.update(f"tests/pipeline_eval/{name}" for name in ("test_strict_packed_0107.py", "test_packed_combined_input.py"))
    if (not set(changed) <= allowed or root.parent.resolve(strict=True) != Path("/dev/shm") or
            subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True)):
        raise ValueError("Expected the frozen merged entry and a fresh tmpfs output")
    paired.verified_scope(PRIOR/RECORDING.name, RECORDING)
    archived = paired.archived(EARLIER)
    if not archived["passed"] or machine != archived["binding"]["machine"]:
        raise ValueError("Original adaptive comparison or low-priority machine settings changed")
    session, members = input_inventory()
    observed = residency(members)
    if not paired.is_resident(observed) or session != archived["binding"]["session"]:
        raise ValueError("Require the whole original staged source resident before conversion")
    clip = dict(recording=str(RECORDING), compressed_bytes=CASE.compressed_bytes, issued=CASE.windows,
                manifests=[dict(path=str(members["manifest"][0]), digest=members["manifest"][2])])
    root.mkdir()
    setup = elapsed(begin)
    packed, dirs, codec = strict.transform(root, clip, observed, member_count=1, variable_extents=True)
    candidate = partial(candidate_command, packed=packed, reference=archived["binding"]["commands"]["candidate"])
    write(root/"plan.json", dict(revision=revision, runtime_base_revision=MERGED, checkout=tree, source_sha256=paired.digest(paired.HERE/SOURCE),
         original=clip, named_and_ordinary_reference_sha256=EARLIER[1], admission_cost=setup,
         source_residency=observed, derivative_request=packed, machine=machine, launch_order=paired.ORDER))
    before = strict.resident_packed(Path(packed["map"]).parent, dirs, codec)
    started = clocks()
    paired.launch(root/"pair", candidate_factory=candidate,
                  extra_sources=(SOURCE, "north_strict_read.py", "packed_combined_input.py", "seekable_member.py",
                                 "seekable_eight_raw.py", "ci16_packing.c", *adaptive.ADAPTER))
    launch_cost = elapsed(started)
    after = strict.resident_packed(Path(packed["map"]).parent, dirs, codec)
    write(root/"paid.json", dict(packed_before=before, packed_after=after, pair_wall_including_setup_ns=launch_cost["wall_ns"],
         pair_orchestration_cpu_ns=launch_cost["cpu_ns"], clock_from_admission_through_pair_seal=elapsed(begin)))


def signed_schedule(probes, index_rows):
    by_sample = {row["acquisition"]["sample_start"]: str(row["sequence"]) for row in index_rows}
    visits = {}
    for row in probes:
        identity = tuple(row[key] for key in ("channel", "edge", "actual_rf_hz", "valid_start_counter"))
        visit = visits.setdefault(row["visit_index"], (identity, set()))
        if visit[0] != identity or row["receiver_id"] in visit[1]:
            raise ValueError("Original stereo opportunities do not share unique visit clocks")
        visit[1].add(row["receiver_id"])
    counts, apertures = Counter(), {}
    for (_, (identity, radios)) in sorted(visits.items()):
        stream, stamp = identity[:3], identity[3]
        sequence = by_sample[stamp]
        if radios != {0, 1} or sequence in apertures:
            raise ValueError("Require both original radio opportunities on each admitted visit")
        apertures[sequence] = "full" if counts[stream] % 8 == 0 else "short_primary"
        counts[stream] += 1
    return apertures


def complete_reader(audit, build, expected):
    if (not audit.get("strict_packed_eight") or audit["fallback"] is not None or audit["original_windows"] != 0 or
            audit["mapped_members"] != 1 or len(audit["members"]) != 1):
        return False
    item, = audit["members"]
    counts = Counter(expected.values())
    full, short = counts["full"], counts["short_primary"]
    return (item["state"] == "strict-packed-eight" and item["loads"] == expected
            and item["encoded_blocks"] == 2*build["original"]["window_count"]
            and item["seek_sha256"] == build["binding"]["seek_sha256"]
            and item["original_decoded_sha256"] == build["original"]["uncompressed_sha256"]
            and item["checks"]["payload_bytes"] == build["checked_derivative"]["payload_bytes"]
            and item["checks"]["full_checks"] == full and item["checks"]["frames"] == 2*full+short
            and item["checks"]["decoded_bytes"] == 1_600_000*full + 640_000*short)


def score(root, output):
    from packed_combined_input import VARIABLE_EIGHT_SCHEMA
    from seekable_member import EIGHT_MS_SAMPLES, SAMPLE_BYTES

    with TemporaryDirectory(dir="/dev/shm") as stage:
        tmp = Path(stage)/"score.json"
        withhold.score(root/"pair", tmp)
        proof = read(tmp)
    conversion, paid, plan = (read(root/f"{name}.json") for name in ("conversion", "paid", "plan"))
    build, = conversion["sections"]
    index = root/"conversion"/build["binding"]["directory"]/"source-index.jsonl"
    rows = [json.loads(line) for line in checked(index, build["original"]["index_sha256"].removeprefix("sha256:")).splitlines()]
    expected = signed_schedule(proof["native"]["candidate"]["source"]["probes"], rows)
    raw = proof["pair"]["modes"]["candidate"]["bootstrap"]
    audit = raw["packed_ci16_input"]
    empty_parts = sum((row["payload_bytes"] == 0) + (row["payload_bytes"] <= EIGHT_MS_SAMPLES*SAMPLE_BYTES) for row in rows)
    exclusions = {mode: document["provenance"]["excluded_windows"] for mode, document in proof["native"].items()}
    excluded = [row for row in rows if str(row["sequence"]) not in expected]
    checks = dict(full_original_and_packed_readback=(conversion["independent_check"] and len(rows) == CASE.windows and
                  build["checked_derivative"]["full_checks"] == CASE.windows and
                  build["checked_derivative"]["decoded_bytes"] == build["original"]["uncompressed_bytes"]),
                  strict_verified_before_withhold=(complete_reader(audit, build, expected) and len(expected) == INPUTS.admitted
                  and raw["raw_acquisitions"] == raw["verified_handoffs"] == 1
                  and audit["schema"] == VARIABLE_EIGHT_SCHEMA and audit["members"][0]["empty_parts"] == empty_parts
                  and audit["map_sha256"] == conversion["request"]["map_sha256"]),
                  original_exclusions=(exclusions["candidate"] == exclusions["stock"] and
                      [(row["sequence"], row["iq_sha256"]) for row in excluded] ==
                      [(row["visit"], row["iq_sha256"]) for row in exclusions["candidate"]]),
                  exact_expected_null_arms=all(set(mode["science"]["arms"]) == {"c0", "fitted_c"}
                  and all(arm["latlon"] is None and arm.get("rf_rms_hz") is None for arm in mode["science"]["arms"].values())
                  for mode in proof["pair"]["modes"].values()))
    clocks = {mode: values["clock"] for mode, values in proof["pair"]["clocks"].items()}
    conversion_wall = conversion["total_including_compiler_and_verification"]["wall_ns"]/1e9
    count = clocks["candidate"]["elapsed_s"]
    archived = paired.archived(EARLIER)
    write(output, dict(pass_through=proof["passed"] and all(checks.values()), strict_checks=checks, plan=plan,
         timed=clocks, measured=proof, conversion=conversion, paid=paid, expected_apertures=expected,
         excluded_original=[dict(sequence=row["sequence"], sample_count=row["sample_count"],
                                 quality_flags=row["acquisition"]["quality_flags"]) for row in excluded],
         time=dict(conversion_wall_s=conversion_wall, first_use_wall_s=conversion_wall+count,
                   prebuilt_speedup=clocks["stock"]["elapsed_s"]/count,
                   legacy_speedup=clocks["stock"]["elapsed_s"]/(conversion_wall+count),
                   prior_ordinary=archived["pair"]["clocks"]["candidate"]["clock"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.output is not None and not args.output.resolve().is_relative_to(args.root.resolve()):
        score(args.root, args.output)
    else:
        parser.error("provide a score path outside the sealed output")
