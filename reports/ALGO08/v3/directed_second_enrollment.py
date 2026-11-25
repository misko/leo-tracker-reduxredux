"""Read only frozen order, filesystem inventory metadata and the planned 0208 extents."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path


CAMPAIGN_PLAN_SHA = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
EXECUTION_ORDER_SHA = "143590d0a3afbbac6c9bdc448ce94661ac6df0004816514da7098527f51bd85a"
PROSPECT_PLAN_SHA = "0c99cbda498845f89f3a0385191b4d8c8864f1bdfe177c7b0f8c9d24346563cb"
PROSPECT = "DS30-0208"
CASES = ("DS30-0107","DS30-0049","DS30-0019","DS30-0274","DS30-0452","DS30-0086","DS30-0339",
         "DS30-0218","DS30-0442","DS30-0008","DS30-0016",PROSPECT,"DS30-0163","DS30-0169","DS30-0419")
FIRST_SIX = tuple(f"iq-{i:06}.ci16.zst" for i in range(6))
INDEXES = tuple(f"windows-{i:06}.jsonl" for i in range(6))


def load(path, expected):
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected:
        raise ValueError(f"The frozen enrollment changed at {path}")
    return json.loads(body)


def execution_order(plan):
    cases = [entry["case"] for entry in plan["cases"]]
    if len(cases) != 455 or len(set(cases)) != 455 or not set(plan["smoke"]) <= set(cases):
        raise ValueError("Require the exact distinct field cohort and enrolled first smoke pair")
    return [*plan["smoke"],*(case for case in cases if case not in plan["smoke"])]


def staged_names(tsv, case_by_recording):
    """Count each recording copy separately using directory names and sizes alone."""
    copies = defaultdict(dict)
    for line in tsv.splitlines():
        name,bytes_ = line.rsplit("\t",1)
        path = Path(name)
        if not any(path.is_relative_to(root) for root in ("/tmp","/dev/shm")):
            raise ValueError("The census must stay on the explicitly permitted local RAM roots")
        marker = path.parent.name
        if marker.removesuffix("-segment-00000000") not in case_by_recording:
            continue
        if not marker.endswith("-segment-00000000") or not path.name.endswith(".ci16.zst"):
            continue
        case = case_by_recording[marker.removesuffix("-segment-00000000")]
        if path.name not in FIRST_SIX:
            continue
        size = int(bytes_)
        if size == 0:
            continue
        members = copies[case].setdefault(str(path.parent), {})
        if path.name in members or size < 0:
            raise ValueError("Duplicate or invalid nominal member in one stage")
        members[path.name] = size
    return dict(copies)


def first_six_book(book):
    recording = Path(book["expected"]["recording"]).name
    prefix = f"{recording}-segment-00000000"
    if not recording.endswith("-lower"):
        raise ValueError("The frozen lower-pilot asset does not apply to this case")
    expected = {"manifest": {"manifest.json"}, "payload": set(FIRST_SIX), "index": set(INDEXES)}
    sizes, counts, seen, prefix_targets = Counter(), Counter(), set(), []
    for row in book["files"]:
        relative = Path(row.get("relative") or "-")
        kind = row["kind"]
        if relative.parent != Path(prefix) or relative.name not in expected.get(kind,set()):
            continue
        if (relative in seen or row["size"] <= 0 or len(row["sha256"]) != 71
                or Path(row["target"]) != Path("recording")/recording/relative):
            raise ValueError("The enrolled prefix has a duplicate, invalid or relocated extent")
        seen.add(relative)
        sizes[kind] += row["size"]
        counts[kind] += 1
        prefix_targets.append(row["target"])
    if len(seen) != 13 or counts != Counter(manifest=1,payload=6,index=6):
        raise ValueError("The scheduled prospect does not bind all six original members and indexes")
    return dict(counts=dict(counts),bytes=dict(sizes),total_bytes=sum(sizes.values()),targets=prefix_targets)


def inventory(plan, book, case_metadata, local_tsv, stage_root):
    order = execution_order(plan)
    if sha256(("\n".join(order)+"\n").encode()).hexdigest() != EXECUTION_ORDER_SHA:
        raise ValueError("The frozen field execution order changed")
    by_case = {row["case"]:row for row in plan["cases"]}
    stage = staged_names(local_tsv,{Path(row["recording"]).name:row["case"] for row in plan["cases"]})
    selected = {}
    for case in CASES:
        row = by_case[case]
        attempts = {entry["algorithm"]:{key:entry[key] for key in ("admission_state","verified_pair","attempt")}
                    for entry in case_metadata if entry["case"] == case}
        if set(attempts) != {"installed","successor"}:
            raise ValueError("Expected both official roles in the sanitized metadata")
        selected[case] = dict(execution_rank=order.index(case)+1,authorized_visits=row["window_count"],
                              scheduled_edge=Path(row["recording"]).name.rsplit("-",1)[-1],
                              nominal_first_six_by_local_directory=stage.get(case,{}),field=attempts)
    if order.index(PROSPECT)+1 != 96 or book["rank"] != 96 or book["case"] != PROSPECT:
        raise ValueError("The prospect must remain the existing rank-96 booking")
    prefix = first_six_book(book)
    fulfilment = [name for name in prefix["targets"] if (stage_root/name).is_file()]
    return dict(execution_order_sha256=EXECUTION_ORDER_SHA,campaign_plan_sha256=CAMPAIGN_PLAN_SHA,
                no_positions_in_selection=True,nominal_local_matches=selected,
                all_recognized_canonical_local_copies=stage,
                future_prospect=dict(case=PROSPECT,execution_rank=96,schedule_sha256=PROSPECT_PLAN_SHA,
                    total_copy_bytes=book["bytes"],first_six=prefix,first_six_present_in_destination=len(fulfilment),
                    target=str(stage_root),complete_receipt=(stage_root/"cache-capture-result.json").is_file()),
                waveform_payload_bytes_read=0,catalogue_body_bytes_read=0,new_payload_copy_bytes=0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("official_plan",type=Path)
    cli.add_argument("scheduled_cache_enrollment",type=Path)
    cli.add_argument("sanitized_official_roles",type=Path)
    cli.add_argument("local_census_tsv",type=Path)
    cli.add_argument("stage_destination",type=Path)
    args = cli.parse_args()
    report = inventory(load(args.official_plan,CAMPAIGN_PLAN_SHA),load(args.scheduled_cache_enrollment,PROSPECT_PLAN_SHA),
                       json.loads(args.sanitized_official_roles.read_bytes()),args.local_census_tsv.read_text(),
                       args.stage_destination)
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False))
