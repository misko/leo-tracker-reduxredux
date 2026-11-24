"""Summarize paid lookahead scopes from signed result metadata only."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from statistics import median


PREFETCH_PIN = "05b3b619429e1e35c9e9f811b3a68e68df6a6f6b37e7c05338dccd91fb0db8cc"


def read(path):
    body = path.read_bytes()
    return json.loads(body), "sha256:" + sha256(body).hexdigest()


def envelope(members, metric):
    points = [row["complete_encoded_auth"][metric] for row in members]
    return dict(total=sum(points), median=median(points), minimum=min(points), maximum=max(points)) if points else {}


def scope(members):
    return dict(count=len(members), bytes=sum(row["encoded"] for row in members),
                encoded_auth={key: envelope(members, key) for key in ("cpu_ns", "wall_ns", "input_blocks")},
                positive_input_block_members=sum(row["complete_encoded_auth"]["input_blocks"] > 0 for row in members))


def characterize(folder, *, identity=None):
    source, source_pin = read(folder / "legacy-original-acquisition.json")
    audit, audit_pin = read(folder / "unified-short-bootstrap.json")
    receiver = audit["receiver_audit"]
    stats = audit["prefetch"]
    authority = source["finished_raw_authority"]
    if (authority != receiver["recording_authority"]
            or audit["prefetch_sources"]["receiver_member_prefetch"] != PREFETCH_PIN
            or (identity is not None and (authority, audit["native_sha256"]) != identity)):
        raise ValueError("Archived acquisition witness changed source or implementation")
    demand, speculative = [], []
    for row in source["members"]:
        (demand if row["chunk_index"] == 0 else speculative).append(row)
    demand, speculative = scope(demand), scope(speculative)
    if (stats["submitted"] != stats["hits"] or stats["fallback"]
            or (speculative["count"], speculative["bytes"]) != (stats["hits"], stats["hit_bytes"])):
        raise ValueError("Cannot identify segment starts and successful lookahead in archived roster")
    return dict(raw_authority=authority, native_sha256=audit["native_sha256"],
                witness_sha256=dict(member=source_pin, bootstrap=audit_pin),
                prefetch_sources=audit["prefetch_sources"], prefetch=stats, demand=demand, speculative=speculative,
                native_cpu_s=sum(receiver["native"]["native_cpu_ns"].values()) / 1e9,
                native_wall_s=sum(receiver["native"]["native_wall_ns"].values()) / 1e9,
                acquisition=audit["phases"]["authenticated_raw_acquisition"])


def compare_campaign(root, cases):
    body = (root / "rows.jsonl").read_bytes()
    selected = [r for r in map(json.loads, body.splitlines()) if r["case"] in cases and r.get("verified_pair")]
    matched = {}
    for row in selected:
        case, algo = row["case"], row["algorithm"]
        result = root / row["attempt"]
        if not result.resolve().is_relative_to((root / "cases" / case / algo).resolve()):
            raise ValueError("Selected result path is outside the assigned attempt")
        receipt, pin = read(result)
        if pin != row["attempt_result_sha256"]:
            raise ValueError("Selected attempt changed after verification")
        pair = matched.setdefault(case, {})
        if algo in pair:
            raise ValueError("Expected unique paired attempt")
        pair[algo] = dict(elapsed_s=row["elapsed_s"], cpu_s=row["cpu_s"], outcome=row["outcome"],
                          generation=row["generation"], process=receipt["process"], result_sha256=pin)
        if algo == "successor":
            identity = (receipt["raw_identity"]["raw_authority_sha256"], receipt["native_sha256"])
            pair[algo].update(characterize(result.parent / "publication", identity=identity))
    if set(cases) != set(matched) or any(set(pair) != {"installed", "successor"} for pair in matched.values()):
        raise ValueError("Expected exact verified pair coverage for the selected cases")
    return dict(source_rows_sha256="sha256:" + sha256(body).hexdigest(), paired=matched)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("campaign", type=Path)
    cli.add_argument("cases", nargs="+")
    cli.add_argument("--resident", type=Path)
    cli.add_argument("--archived-attempt", type=Path)
    options = cli.parse_args()
    audit = compare_campaign(options.campaign, options.cases)
    if options.resident:
        audit["resident"] = characterize(options.resident)
    if options.archived_attempt:
        receipt, pin = read(options.archived_attempt / "result.json")
        case = options.archived_attempt.parent.parent.name
        successor = audit["paired"][case]["successor"]
        identity = (successor["raw_authority"], successor["native_sha256"])
        audit["earlier_successor_attempt"] = dict(case=case, attempt=options.archived_attempt.name,
            observed_outcome=receipt["outcome"], process=receipt["process"], result_sha256=pin,
            **characterize(options.archived_attempt / "publication", identity=identity))
    print(json.dumps(audit, sort_keys=True, indent=2, allow_nan=False))
