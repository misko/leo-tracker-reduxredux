"""Count selected and solver-owned carrier ranks using frozen v3 metadata."""

import argparse
import gzip
from collections import Counter
from hashlib import sha256
from inspect import getsourcefile
import json
from pathlib import Path


CASES = ("DS30-0008", "north-containing", "south-containing")
ARMS = ("c0", "fitted_c")
APERTURE = Path(__file__).resolve().parent / "measurements/aperture.json.gz"
APERTURE_SHA = "15a4e12381055327d19467fca6c2d16ab3f0d7a4b44698d20d38e42ce3359540"
SOURCE_PINS = {
    "frequency_evidence": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
    "winning_observations": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "owner_digest": "5dd6dbc63a4078e4b7fffcf10237d4f92429a1ea07d585eb3a49d0eca02cae2b",
}
OBSERVATION_FIELDS = ("receiver", "channel", "time_s", "measured_cfo_hz")


def digest(blob):
    return sha256(blob).hexdigest()


def pinned_aperture():
    compressed = APERTURE.read_bytes()
    if digest(compressed) != APERTURE_SHA:
        raise ValueError("Aperture archive differs from the frozen canonical owners")
    return json.loads(gzip.decompress(compressed))["cases"]


def functions():
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.presentation.localization_v3 import owner_digest

    implementations = frequency_evidence, winning_observations, owner_digest
    if {fn.__name__: digest(Path(getsourcefile(fn)).read_bytes()) for fn in implementations} != SOURCE_PINS:
        raise ValueError("The released observation and ownership mapping sources changed")
    return implementations


def factor_rank(probe):
    factors = probe["candidates"]
    if not factors:
        return None
    if len(factors) != 1 or factors[0]["candidate_rank"] not in (0, 1):
        raise ValueError("Expected one selected primary or residual factor per opportunity")
    return factors[0]["candidate_rank"]


def joined_owners(probes, evidence_ids, observations, packet, owner_digest):
    native_indices = {"sha256:" + digest(name.encode()): i for i, name in enumerate(evidence_ids)}
    reverse = {tuple(obs[key] for key in OBSERVATION_FIELDS): obs["observation_id"] for obs in observations}
    if len(native_indices) != len(probes) or len(reverse) != len(observations):
        raise ValueError("Canonical observation keys do not determine unique original opportunities")
    result = {}
    for arm in ARMS:
        catalog, by_index = {}, {}
        for *key, norad in packet["owner_rows"][arm]:
            if tuple(key) not in reverse:
                raise ValueError(f"No exact native observation for {arm} owner {tuple(key)!r}")
            observation = reverse[tuple(key)]
            if observation in catalog:
                raise ValueError("Duplicate owner in the archived canonical arm")
            catalog[observation] = norad
            index = native_indices[observation]
            rank = factor_rank(probes[index])
            if rank is None:
                raise ValueError("Owned opportunity lacks its original selected factor")
            by_index[index] = dict(observation_id=observation, norad=norad, rank=rank)
        if owner_digest(catalog) != packet["owners"][arm]:
            raise ValueError("Exact native time and frequency join failed to reconstruct owner digest")
        result[arm] = by_index
    return result


def canonical_owners(native, packet, identity, expected):
    if packet["identity"] != identity or packet["owners"] != expected["owners"]:
        raise ValueError("Archived full ownership does not describe the installed native packet")
    frequency_evidence, winning_observations, owner_digest = functions()
    evidence, _, _ = frequency_evidence(native)
    observations, _ = winning_observations(native)
    return joined_owners(native["source"]["probes"], evidence.ids, observations, packet, owner_digest)


def census(probes, by_arm, indices):
    ranks = {i: factor_rank(probes[i]) for i in indices}

    def measures(values):
        counts = Counter(values)
        return dict(total=counts[0] + counts[1], rank0=counts[0], rank1=counts[1])

    return dict(opportunities=len(ranks), selected=measures(ranks.values()),
                owned={arm: measures(row["rank"] for i, row in owners.items() if i in ranks)
                       for arm, owners in by_arm.items()})


def run(output):
    from aperture_ingress import PREFIX
    from aperture_trial import inputs, machine, write
    from leo.contracts.digests import canonical_digest

    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(value != "1" for value in system["threads"].values())):
        raise RuntimeError("Expected CPU 2 and one low-priority numerical thread")
    packets = pinned_aperture()
    cases = {}
    for case in CASES:
        try:
            if case not in packets:
                raise FileNotFoundError(f"No {case} ownership in {APERTURE}")
            native, _, _, expected, identity = inputs(case)
        except FileNotFoundError as exc:
            cases[case] = dict(status="missing", reason=str(exc))
            continue
        packet = packets[case]["full"]
        owners = canonical_owners(native, packet, identity, expected)
        probes = native["source"]["probes"]
        slices = dict(full=census(probes, owners, range(len(probes))))
        if case == "DS30-0008":
            prefix = {i for i, row in enumerate(probes) if row["visit_index"] < PREFIX}
            slices["first_128"] = census(probes, owners, prefix)
            slices["after_first_128"] = census(probes, owners, set(range(len(probes))) - prefix)
        cases[case] = dict(status="joined", identity=identity, owner_digests=packet["owners"],
                           selected_probe_digest=canonical_digest(probes), slices=slices)
    write(output, dict(machine=system, case_order=list(CASES), aperture_sha256=APERTURE_SHA,
                       observation_source_digests=SOURCE_PINS, cases=cases))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
