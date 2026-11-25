"""Prepare, run and score the unchanged directed trial on the booked detached stage."""

import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import directed_second_enrollment as book
from . import empty_lane_directed_replay as frozen
from .directed_stage_cache_reader import CacheReader, CacheSourceUnavailable, Extent, ordered_hashes, signed_windows
from .empty_graph_rescue import proposals
from .track_cfo_denoise import graph_pins


CASE = book.PROSPECT
HERE = Path(__file__).resolve().parent
CAMPAIGN = frozen.arrival.FIELD
BOOK = Path("/srv/postgres-nvme/leo-ds30-0208-cache-gate/enrollment.json")
STAGE = Path("/srv/postgres-nvme/leo-ds30-0208-cache-only")
WINDOWS = 384
SIGNED_ORDER = "91e670c5646af1984204a24ca1205cf2d23c64838a5d80dd545489017af81028"
signed = frozen.arrival.signed


def timed(start):
    wall, cpu, blocks = start
    return dict(wall_ns=perf_counter_ns()-wall,cpu_ns=process_time_ns()-cpu,
                input_blocks=getrusage(RUSAGE_SELF).ru_inblock-blocks)


def start_clock():
    return perf_counter_ns(),process_time_ns(),getrusage(RUSAGE_SELF).ru_inblock


def source_pins():
    return {name:frozen.tag(HERE/name) for name in (
        "directed_0208_reuse.py","directed_stage_cache_reader.py","directed_second_enrollment.py",
        "directed-second-enrollment-protocol.md")}


def authority(roster, capture_pin):
    case = CAMPAIGN/"cases"/CASE
    if STAGE.resolve(strict=True) != STAGE or case.resolve(strict=True) != case:
        raise ValueError("A detached or official authority path was replaced by an alias")
    capture = book.load(STAGE/"cache-capture-result.json",capture_pin)
    pair_body = (case/"pair.json").read_bytes()
    pair_pin = sha256(pair_body).hexdigest()
    pair = json.loads(pair_body)
    signed_original = signed.document(case/"authority.json",pair["authority_sha256"])
    if (roster["case"] != CASE or roster["rank"] != 96 or not pair["verified_pair"] or pair["state"] != "observed_pair"
            or capture["case"] != CASE or capture["state"] != "complete" or capture["origin"] != "strict_RWF_NOWAIT"
            or capture["pair_sha256"] != pair_pin or capture["authority"] != signed_original
            or capture["zero_input_blocks_per_admitted_source_read"] is not True
            or capture["copied_bytes"] != roster["bytes"] or capture["completed"] != [row["target"] for row in roster["files"]]
            or any(signed_original[key] != value for key,value in roster["expected"].items())
            or signed_original["region_sha256"] != roster["offer_sha256"]):
        raise ValueError("Require the complete independently captured stage and matched official pair")
    generation = pair["generation"]
    outputs = set(pair["attempt_result_sha256"])
    if type(generation) is not int or generation < 1 or outputs != {"installed","successor"}:
        raise ValueError("The official pair must supply both original generation-matched arms")
    return pair,pair_pin,case,signed_original


def output(pair, case, role, original):
    folder = case/role/f"attempt-{pair['generation']:06d}"
    result = signed.document(folder/"result.json",pair["attempt_result_sha256"][role])
    if (result["algorithm"] != role or result["authority_sha256"] != pair["authority_sha256"]
            or result["raw_identity"] != original or result["process"]["exit_code"] or not result["native_sha256"]):
        raise ValueError("A matched original raw result no longer qualifies")
    return result,folder/"publication"


def candidate(pair, case, original):
    result, publication = output(pair,case,"successor",original)
    note = signed.document(publication/"unified-short-bootstrap.json")
    native,_,_ = signed.qualified_candidate(publication,note,result["native_sha256"],original["region_sha256"])
    source = native["source"]
    recipe = note["held_anchor_route"]["receiver_recipe"]
    if (source["session_id"] != original["session_id"] or source["input_manifest_sha256"] != original["inventory_sha256"]
            or source["raw_recording_authority_digest"] != original["raw_authority_sha256"]
            or recipe["rule"] != ["full",*(["short_primary"]*7)]
            or recipe["streams"] != ["edge","channel","actual_rf_hz"]
            or native["provenance"]["detector_sha256"] != signed.canonical(recipe)):
        raise ValueError("The original frozen aperture schedule or raw authority changed")
    return native,result["native_sha256"]


def prefix(roster):
    section = book.first_six_book(roster)
    selected = {Path(row["target"]).name:Extent(row["size"],row["sha256"],row["kind"]) for row in roster["files"]
                if row["target"] in section["targets"]}
    paths = {STAGE/target for target in section["targets"]}
    parents = {path.parent for path in paths}
    if len(parents) != 1 or len(selected) != 13:
        raise ValueError("The original six-member prefix must belong to one direct segment")
    directory, = parents
    device = STAGE.parent.stat().st_dev
    if STAGE.resolve(strict=True) != STAGE or directory.resolve(strict=True) != directory or directory.stat().st_dev != device:
        raise ValueError("The booked prefix is not on the original detached NVMe stage")
    return directory,selected,paths


def prepare(root, roster, capture_pin):
    clock = start_clock()
    pair,pair_pin,case,original = authority(roster,capture_pin)
    native,native_pin = candidate(pair,case,original)
    graph_pins()
    lanes = signed.opportunities(native)
    _,pieces,scope = signed.graph(native,lanes)
    proposed = proposals(lanes,pieces)
    empty, predictions, projection = frozen.arrival.prepare(proposed,lanes)
    visits,queries = frozen.project(lanes,predictions)
    targets = {row["id"] for row in queries}
    delays = {key:proposed["opportunities"][key]["brackets"][0]["right"]["counter"]-lanes[key]["counter"]
              for key in targets}
    if any(not 0 <= int(visit) < WINDOWS for visit in visits):
        raise ValueError("Query projection exceeded the frozen prefix")
    if frozen.tag(Path(frozen.__file__)) != SIGNED_ORDER:
        raise ValueError("The original directed waveform/score entry changed")
    plan = dict(case=CASE,pair_sha256=pair_pin,capture_sha256=capture_pin,candidate_native_sha256=native_pin,
                original_source=dict(authority=original),admitted_visits=visits,queries=queries,
                total_issued_visits=WINDOWS,graph=scope,projection=projection,right_wait_samples=delays,
                prefix_empty_short=sum(lanes[key]["row"]["visit_index"] < WINDOWS for key in empty),
                directed_library_sha256=frozen.LIBRARY_PIN,asset_sha256=frozen.ASSET_PIN,
                phase_order=list(frozen.arrival.PHASES),worker_sha256=SIGNED_ORDER,sources=source_pins())
    root.mkdir(mode=0o700)
    frozen.prefix.write(root/"plan.json",plan)
    pin = frozen.tag(root/"plan.json")
    frozen.prefix.write(root/"proposal-clock.json",dict(**timed(clock),plan_sha256=pin,queries=len(queries)))
    return pin


def reference(pair, case, original):
    result, publication = output(pair,case,"installed",original)
    # Require full owner rows bound to the official two-arm digests. A digest alone is insufficient.
    owners = frozen.arrival.named_rows(CASE,result)
    if owners is None:
        raise ValueError("The original matched control lacks exact archived owners for both arms")
    files = tuple((publication/"fast-scan-automatic-work").glob("*/detections.json"))
    if (len(files) != 1 or files[0].resolve(strict=True) != files[0]
            or frozen.tag(files[0]) != result["native_sha256"].removeprefix("sha256:")):
        raise ValueError("The exact archived installed detector prerequisite is absent or changed")
    return result,publication,signed.owners(owners,result["evidence"]["owners"])


def audit_paths(reader=None):
    def guard(event,args):
        if event != "open" or not isinstance(args[0],(str,bytes)):
            return
        path = Path(os.fsdecode(args[0]))
        resolved = path if not path.is_absolute() else path.resolve()
        if resolved.is_relative_to("/srv/bulk") or resolved.is_relative_to("/mnt/qnap01"):
            raise ValueError("The detached read cannot access the archive or recording backing")
        if path.name.endswith((".ci16.zst",".tle",".tle.gz")):
            if (reader is None or path.parts != (reader.opening,) or not isinstance(args[2],int)
                    or args[2] & os.O_ACCMODE != os.O_RDONLY):
                raise ValueError("Only the exact directory-descriptor cache port may read waveform bytes")
    sys.addaudithook(guard)


def replay(root, roster, capture_pin, plan_pin, event, driver):
    from leo.storage.errors import RecordingStoreError

    from .directed_replay_0049_ram import DRIVER, DRIVER_PIN, allowed_event

    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS,0) != 15:
        raise ValueError("The separately authorized replay must use the regular low-priority CPU2 lease")
    if frozen.tag(DRIVER) != DRIVER_PIN:
        raise ValueError("The live field controller source changed")
    clock = start_clock()
    plan = book.load(root/"plan.json",plan_pin)
    pair,pair_pin,case,original = authority(roster,capture_pin)
    if (plan["pair_sha256"] != pair_pin or plan["capture_sha256"] != capture_pin or plan["case"] != CASE
            or plan["original_source"]["authority"] != original or plan["worker_sha256"] != SIGNED_ORDER
            or frozen.tag(Path(frozen.__file__)) != SIGNED_ORDER or plan["sources"] != source_pins()):
        raise ValueError("The resident replay differs from the sealed original candidate queries")
    reference(pair,case,original)
    directory,extents,paths = prefix(roster)
    manifest_pin = extents["manifest.json"].sha256
    reader = CacheReader(directory,extents)
    audit_paths(reader)
    with frozen.LOCK.open("rb") as lease:
        fcntl.flock(lease,fcntl.LOCK_EX | fcntl.LOCK_NB)
        age = allowed_event(event,driver)
        frozen.prefix.write(root/"replay-intent.json",dict(event=event,plan=plan_pin,age_ns=age))
        try:
            with signed_windows(reader), patch.object(frozen.prefix,"MANIFEST_PIN",manifest_pin):
                witness = ordered_hashes(directory,manifest_pin)
                mounted = plan | dict(original_source=plan["original_source"] | dict(
                    recording=str(directory),window_hashes=witness,files=list(map(str,sorted(paths)))))
                measured = frozen.take(mounted)
                reader.verify_complete()
        except (OSError,ValueError,RecordingStoreError) as error:
            frozen.prefix.write(root/"replay-refusal.json",dict(admitted=False,reason=str(error),
                                clock=timed(clock),cache=reader.receipt(),plan_sha256=plan_pin))
            raise
    archive = root/"waveforms.json"
    frozen.prefix.write(archive,dict(admitted=True,verified_prefix_bytes=reader.bytes,
                        plan_sha256=plan_pin,cache=reader.receipt(),**measured))
    pin = frozen.tag(archive)
    frozen.prefix.write(root/"replay-clock.json",dict(**timed(clock),plan_sha256=plan_pin,waveform_sha256=pin))
    return pin


def score(root, roster, capture_pin, plan_pin, waveform_pin):
    plan = book.load(root/"plan.json",plan_pin)
    wave = book.load(root/"waveforms.json",waveform_pin)
    pair,pair_pin,case,original = authority(roster,capture_pin)
    if (plan["pair_sha256"] != pair_pin or plan["capture_sha256"] != capture_pin or wave["plan_sha256"] != plan_pin
            or plan["sources"] != source_pins()):
        raise ValueError("The score must bind the independently sealed forecasts and waveform outcomes")
    stock,publication,owners = reference(pair,case,original)
    native,native_pin = candidate(pair,case,original)
    installed = signed.read_native(publication,stock["native_sha256"])
    if native_pin != plan["candidate_native_sha256"] or installed["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
        raise ValueError("Use the original full detector on the same input")
    old, new = map(signed.opportunities,(installed,native))
    signed.bind_pair(installed,native,old,new)
    missed = {oid for oid,lane in new.items() if lane["short"] and lane["factor"] is None
              and lane["row"]["visit_index"] < WINDOWS and old[oid]["factor"] is not None}
    proposed = {row["id"]:dict(centers_hz=[row["hz"]],phase=row["phases"]) for row in plan["queries"]}
    summary = dict(installed_sha256=stock["native_sha256"],prefix_missing=len(missed),
                   prefix_owned_missing={arm:len(missed & rows.keys()) for arm,rows in owners.items()},
                   proposal_only=frozen.arrival.score_group(missed,proposed,old),
                   owner_proposal_only={arm:frozen.arrival.score_group(missed,proposed,old,rows.keys())
                                        for arm,rows in owners.items()})
    with patch.object(frozen,"comparison",lambda _: (summary,old,missed,owners)):
        result = frozen.score(plan,wave)
    frozen.prefix.write(root/"score.json",result | dict(waveform_sha256=waveform_pin))
    return frozen.tag(root/"score.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare","replay","score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--capture-pin", required=True)
    parser.add_argument("--plan-pin")
    parser.add_argument("--waveform-pin")
    parser.add_argument("--event",type=Path)
    parser.add_argument("--pid",type=int)
    args = parser.parse_args()
    roster = book.load(BOOK,book.PROSPECT_PLAN_SHA)
    if args.action == "prepare":
        audit_paths()
        value = prepare(args.root,roster,args.capture_pin)
    elif not args.plan_pin:
        parser.error("Require the pre-reference sealed plan")
    elif args.action == "replay" and args.event and args.pid:
        value = replay(args.root,roster,args.capture_pin,args.plan_pin,json.loads(args.event.read_bytes()),args.pid)
    elif args.action == "score" and args.waveform_pin:
        audit_paths()
        value = score(args.root,roster,args.capture_pin,args.plan_pin,args.waveform_pin)
    else:
        parser.error("Require the live deferral or the sealed waveform receipt for scoring")
    print(value)
