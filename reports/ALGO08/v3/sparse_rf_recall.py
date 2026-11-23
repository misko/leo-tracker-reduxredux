"""Replay sparse owners and price a metadata-only held-factor coverage ceiling."""

import argparse
from bisect import bisect_left
from collections import defaultdict
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import ARMS, inputs, read, write
from primary_owner_census import canonical_owners, functions, pinned_aperture
from rf_block_trial import run as sparse_run, schedule


HERE = Path(__file__).resolve().parent
FROZEN_BLOCK = HERE / "measurements/rf-block.json"
BLOCK_SHA256 = "0fa1c1ee72b88307d866a627e10495b20f4f15d4e570f26519a7094116f75075"
TRIAL_SHA256 = "831ab10c991e436fa69a09ae4fc3a2f3e32865c1ab4b2121de6167be43f5074a"
CASES = ("DS30-0008", "south-containing")
WINDOWS = (8, 30, 60)
KEYS = {
    "satellite": lambda n, row: (n,),
    "satellite_receiver": lambda n, row: (n, row["receiver"]),
    "satellite_receiver_rf": lambda n, row: (n, row["receiver"], row["rf_hz"]),
}


def check_file(path, expected):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"Frozen sparse experiment changed: {path}")
    return raw


def metadata(native):
    frequency_evidence, _, _ = functions()
    source = native["source"]
    probes = source["probes"]
    ignored_factors = [dict(probe, candidates=[]) for probe in probes]
    blank = dict(native, source=dict(source, probes=ignored_factors))
    evidence, _, _ = frequency_evidence(blank)
    keep, paid, _ = schedule(ignored_factors)
    rows = []
    for name, time_s, probe in zip(evidence.ids, evidence.time_s, ignored_factors, strict=True):
        visit = probe["visit_index"]
        rows.append(dict(observation_id="sha256:" + sha256(name.encode()).hexdigest(),
                         time_s=float(time_s), receiver=probe["receiver_id"], rf_hz=probe["actual_rf_hz"],
                         edge=probe["edge"], channel=probe["channel"], visit=visit,
                         searched=visit in keep, paid=visit in paid))
    return rows


def nearest(times, target):
    k = bisect_left(times, target)
    return min((abs(t - target) for t in times[max(0, k - 1):k + 1]), default=float("inf"))


def incidence(anchors):
    tables = {label: defaultdict(list) for label in KEYS}
    for row in anchors:
        for label, key in KEYS.items():
            tables[label][key(row["norad"], row)].append(row["time_s"])
    for table in tables.values():
        for values in table.values():
            values.sort()
    return tables


def oracle(tables, held):
    totals = {}
    for label, key in KEYS.items():
        table = tables[label]
        distances = [nearest(table.get(key(row["norad"], row), ()), row["time_s"]) for row in held]
        totals[label] = dict(any_time=sum(d != float("inf") for d in distances),
                             **{f"within_{window}_s": sum(d <= window for d in distances)
                                for window in WINDOWS})
    return dict(full_owner_rows=len(held), coverage=totals)


def coverage(meta, sparse, full):
    ids = {row["observation_id"]: row for row in meta}
    if len(ids) != len(meta):
        raise ValueError("Native metadata must uniquely identify each opportunity")
    measurements = {}
    for arm in ARMS:
        anchors = [dict(ids[row["observation_id"]], norad=row["norad"]) for row in sparse[arm]]
        if any(not row["searched"] for row in anchors):
            raise ValueError("A sparse association came from a held visit")
        subjects = {row["observation_id"]: row["norad"] for row in anchors}
        agreed = sum(row["observation_id"] in subjects and subjects[row["observation_id"]] == row["norad"]
                     for row in full[arm].values())
        shared = sum(row["observation_id"] in subjects for row in full[arm].values())
        missed = [dict(meta[i], norad=row["norad"]) for i, row in full[arm].items()
                  if row["observation_id"] not in subjects]
        tables = incidence(anchors)
        parts = dict(searched=[], unpaid_held=[], paid_warmup=[])
        for row in missed:
            key = "searched" if row["searched"] else "paid_warmup" if row["paid"] else "unpaid_held"
            parts[key].append(row)
        measurements[arm] = dict(sparse_owned=len(anchors), full_owned=len(full[arm]), shared=shared,
                                 same_satellite=agreed, changed_satellite=shared-agreed,
                                 sparse_satellites=len(tables["satellite"]),
                                 missing={name: oracle(tables, held) for name, held in parts.items()})
    return measurements


def capture_sparse(case, receipt):
    import blind_joint_trial

    original_configure = blind_joint_trial.configuration
    saved = []
    with ExitStack() as stack:
        def configure():
            publication, specification = original_configure()
            from tools import algo08_position

            original_packet = algo08_position.prepare_packet

            def packet(context, owners, expected, *args, **kwargs):
                output = original_packet(context, owners, expected, *args, **kwargs)
                saved.append((output["rows"], context, expected))
                return output

            stack.enter_context(patch.object(algo08_position, "prepare_packet", packet))
            return publication, specification

        stack.enter_context(patch.object(blind_joint_trial, "configuration", configure))
        sparse_run(case, receipt)
    if len(saved) != 1:
        raise ValueError("Expected exactly one accepted sparse science packet")
    return saved[0]


def trial(case, receipt, output, *, signed_ceiling=None):
    frozen = json.loads(check_file(FROZEN_BLOCK, BLOCK_SHA256))["cases"][case]
    check_file(HERE / "rf_block_trial.py", TRIAL_SHA256)
    if signed_ceiling is not None:
        previous = read(signed_ceiling)
        if previous["case"] != "DS30-0008" or previous["frozen_block_sha256"] != BLOCK_SHA256:
            raise ValueError("Expected the dense metadata-only gate receipt")
        for arm in ARMS:
            held = previous["recall"][arm]["missing"]["unpaid_held"]
            if held["coverage"]["satellite_receiver"]["within_60_s"] * 2 < held["full_owner_rows"]:
                raise ValueError("The dense metadata-only receiver ceiling did not pass")
    sparse, context, states = capture_sparse(case, receipt)
    observed = read(receipt)
    decision = observed["decision"]
    if (observed["input"] != frozen["input"] or observed["mask"] != frozen["mask"]
            or any(decision[k] != frozen["decision"][k] for k in
                   ("arms", "owners", "science", "status", "reason", "associated"))):
        raise ValueError("Sparse experiment no longer matches its frozen results")
    native, _, _, expected, identity = inputs(case)
    meta = metadata(native)
    predicted = {}
    if signed_ceiling is not None:
        from sparse_rf_carrier import propose

        predicted = {arm: propose(context["scan"], states[arm], meta, sparse[arm]) for arm in ARMS}
    # The archive of full owners serves only this scoring boundary.
    archive = pinned_aperture()[case]["full"]
    full = canonical_owners(native, archive, identity, expected)
    result = coverage(meta, sparse, full)
    signed = {}
    if predicted:
        from leo.contracts.digests import canonical_digest
        from sparse_rf_carrier import score

        probes = native["source"]["probes"]
        for arm, proposed in predicted.items():
            held = {row["observation_id"]: (row["norad"], probes[index]["candidates"][0]["fractional_tracking_cfo_hz"])
                    for index, row in full[arm].items() if not meta[index]["paid"]}
            proposals = proposed.pop("proposals")
            signed[arm] = dict(
                **proposed, all_unpaid_lanes=sum(not row["paid"] for row in meta),
                proposal_sha256=canonical_digest(proposals),
                rules={rule: score(rows, held) for rule, rows in proposals.items()},
            )
    write(output, dict(case=case, identity=identity, mask=observed["mask"], sparse=decision,
                       frozen_block_sha256=BLOCK_SHA256, trial_sha256=TRIAL_SHA256,
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       signed_source_sha256=sha256((HERE / "sparse_rf_carrier.py").read_bytes()).hexdigest()
                       if signed else None, recall=result, signed=signed))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=CASES)
    cli.add_argument("receipt", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--signed-ceiling", type=Path)
    trial(**vars(cli.parse_args()))
