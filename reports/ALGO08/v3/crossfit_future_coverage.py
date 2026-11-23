"""Measure whether future-only blocks can be withheld without changing the forward fit input."""

import argparse
from collections import defaultdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import process_time, perf_counter

from aperture_trial import read, write
from dense_geographic_trial import host
from local_future_inputs import MAX_GAP_S, lane, selection
from short_stereo_trial import HERE, load_source


BLOCK_S = 10
FOLD_BUDGET_CPU_S = 2.62
WEAK_FORWARD = Path("/var/tmp/leo-causal-weak-south-nov23/physical")
TRANSFER_FORWARD = Path("/tmp/leo-protected-DS30-0057-01/forward")


def by_block(rows):
    blocks = defaultdict(list)
    for row in rows:
        blocks[int(row["time_s"] // BLOCK_S)].append(row)
    return blocks


def training_rows(blocks, hold):
    return [row for block, rows in sorted(blocks.items()) if abs(block-hold) > 1 for row in rows]


def identifier(session, row):
    return "sha256:" + sha256(f"{session}:{row['receiver_id']}:{row['valid_start_counter']}".encode()).hexdigest()


def erase(native, ids):
    source = native["source"]
    probes = []
    for probe in source["probes"]:
        keep = identifier(source["session_id"], probe) not in ids
        probes.append(probe if keep else dict(probe, candidates=[]))
    return dict(native, source=dict(source, probes=probes))


def eligible_metadata(future, chosen, native):
    peers = defaultdict(list)
    for oid, satellite, role in chosen:
        row = native[oid]
        peers[lane(row)].append((row["time_s"], satellite, role))
    result = {}
    for row in future:
        options = {(satellite, role) for when, satellite, role in peers[lane(row)] if abs(when-row["time_s"]) <= MAX_GAP_S}
        if len(options) == 1:
            satellite, role = options.pop()
            result[row["observation_id"]] = (satellite, row["receiver"], role)
    return result


def count_blocks(native, forward, future, potential, owner_ids):
    blocks = by_block(future)
    original = forward["source"]["probes"]
    session = native["source"]["session_id"]
    result = []
    for block, held in sorted(blocks.items()):
        held_ids = {row["observation_id"] for row in held}
        train = training_rows(blocks, block)
        after_forward, after_future = selection(erase(native, held_ids))
        training = training_rows(by_block(after_future), block)
        changed = [identifier(session, before) for before, after in zip(original, after_forward["source"]["probes"], strict=True) if before != after]
        held_labels = {oid: potential[oid] for oid in held_ids & potential.keys()}
        training_potential = sum(row["observation_id"] in potential for row in train)
        result.append(dict(block=block, seconds=[block*BLOCK_S, (block+1)*BLOCK_S], held=len(held),
                           held_ids=sorted(held_ids), held_metadata_eligible=held_labels, training=len(train),
                           training_metadata_eligible=training_potential, forward_changed=len(changed),
                           forward_owners_affected=len(owner_ids & set(changed)), forward_packet_unchanged=not changed,
                           training_unchanged=training == train,
                           eligible=not changed and training == train and bool(held_labels) and training_potential > 0))
    return result


def observed_inputs(case):
    if case == "DS30-0016":
        _, _, _, pin, offer, native = load_source("physical")
        return native, pin, offer
    from local_future_0057 import inputs

    row, pin, packet, _, _ = inputs("forward")
    return read(packet), pin, row["region"]


def measured_context(case):
    early = case == "DS30-0016"
    directory = WEAK_FORWARD if early else TRANSFER_FORWARD
    trial = read(directory / "joint-research-receipt.json")
    receipt = trial["receipt"]
    actual_terminal = read(directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    if early:
        archive = HERE / "measurements/local-future-repair.json.gz"
        repair = json.loads(gzip.decompress(archive.read_bytes()))["results"]["physical"]
        forward = read(HERE / "measurements/causal-selection-transfer.json")["physical"]
        if forward["decision"] != "complete" or trial["evidence"]["images"] != forward["images"]:
            raise ValueError("Saved weak forward receipt differs from its independent scored publication")
        repair_cost = repair["repair"]["cost"]["cpu_s"]
        pin = repair["policy"]["forward_sha256"]
    else:
        archive = HERE / "measurements/local-future-0057.json.gz"
        prior = json.loads(gzip.decompress(archive.read_bytes()))
        forward = prior["runs"]["forward"]
        if forward["terminal_sha256"] != receipt["terminal_sha256"] or forward["evidence"] != trial["evidence"]:
            raise ValueError("Saved forward receipt differs from the independent DS30-0057 index")
        repair_cost = prior["runs"]["repair"]["repair"]["cost"]["cpu_s"]
        pin = prior["policy"]["forward_sha256"]
    return trial, actual_terminal, pin, repair_cost, sha256(archive.read_bytes()).hexdigest()


def measure(case):
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    started, wall = process_time(), perf_counter()
    native, source, offer = observed_inputs(case)
    previous, terminal, forward_pin, repair_cost, archive = measured_context(case)
    directory = WEAK_FORWARD if case == "DS30-0016" else TRANSFER_FORWARD
    receipt = previous["receipt"]
    detail = FastStandardAnalysisStore(directory).detail(receipt["run_id"])
    forward, future = selection(native)
    if (canonical_digest(native) != source or canonical_digest(forward) != forward_pin
            or canonical_digest(terminal) != receipt["terminal_sha256"] or receipt["region"] != offer
            or detail["terminal_sha256"] != receipt["terminal_sha256"] or receipt["decision"] != "complete"):
        raise ValueError("The original forward packet and its publication no longer bind the scored controls")
    chosen = previous["selected_rows"]
    if chosen["c0"] != chosen["fitted_c"]:
        raise ValueError("Expected the same fixed owner and role witnesses for both calibration arms")
    owners = {oid: sat for oid, sat, _ in chosen["c0"]}
    if len(owners) != len(chosen["c0"]) or any(owner_digest(owners) != arm["owner_sha256"] for arm in detail["arms"].values()):
        raise ValueError("The forward owner witness differs from the sealed figure manifest")
    observed, _ = winning_observations(native)
    potential = eligible_metadata(future, chosen["c0"], {row["observation_id"]: row for row in observed})
    folds = count_blocks(native, forward, future, potential, owners.keys())
    valid = [row for row in folds if row["eligible"]]
    groups = {(sat, receiver) for row in valid for sat, receiver, _ in row["held_metadata_eligible"].values()}
    projected = len(valid)*2*repair_cost
    return dict(case=case, source_sha256=source, forward_sha256=forward_pin, archive_sha256=archive,
                forward_terminal_sha256=receipt["terminal_sha256"], prior_forward_solve_cpu_s=previous["solve"]["cpu_s"],
                future=len(future), metadata_nominable=len(potential), forward_owners=len(owners), blocks=folds,
                eligible_blocks=len(valid), eligible_holdout_groups=len(groups), previous_full_repair_cpu_s=repair_cost,
                projected_extra_cpu_s=projected, projected_limit_cpu_s=FOLD_BUDGET_CPU_S,
                proceed=len(valid) >= 2 and len(groups) >= 2 and projected <= FOLD_BUDGET_CPU_S,
                coverage_cpu_s=process_time()-started, coverage_elapsed_s=perf_counter()-wall)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    out = cli.parse_args().output
    write(out, dict(host=host(), cases=[measure(case) for case in ("DS30-0016", "DS30-0057")],
                   protocol_sha256=sha256(Path(__file__).with_name("crossfit-future-repair-protocol.md").read_bytes()).hexdigest(),
                   coverage_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
