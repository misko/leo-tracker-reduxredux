"""Measure attainable stock observation coverage for every legal survey channel pair."""

import argparse
from collections import defaultdict
from itertools import product
from pathlib import Path

from aperture_trial import configuration, inputs, machine, write
from primary_owner_census import APERTURE_SHA, canonical_owners, pinned_aperture
from survey_channels import choose, group


def coverage(probes, owners, eligible):
    antennas, thirds, frequencies = (defaultdict(set) for _ in range(3))
    count = 0
    for i, owner in owners.items():
        row = probes[i]
        if row["visit_index"] in eligible:
            satellite = owner["norad"]
            antennas[satellite].add(row["receiver_id"])
            thirds[satellite].add(3 * (i // 2) // (len(probes) // 2))
            frequencies[satellite].add(row["actual_rf_hz"])
            count += 1
    return dict(rows=count, satellites=len(antennas),
                both_antennas=sum(len(x) == 2 for x in antennas.values()),
                first_and_last=sum(0 in x and 2 in x for x in thirds.values()),
                multiple_tunings=sum(len(x) >= 2 for x in frequencies.values()))


def pair_census(probes, by_arm):
    actual_visits, frozen = choose(probes)
    stereo = probes[::2]
    prefix = frozen["survey_visits"]
    early = {p["visit_index"] for p in stereo[:prefix]}
    groups = sorted({group(p) for p in stereo[:prefix]})
    middle = (len(groups) + 1) // 2
    pairs = []
    for pair in product(groups[:middle], groups[middle:]):
        chosen = early | {p["visit_index"] for p in stereo[prefix:] if group(p) in pair}
        actual = list(pair) == frozen["selected_groups"]
        if actual and actual_visits != chosen:
            raise ValueError("Census and causal routing disagree")
        pairs.append(dict(channels=pair, paid=len(chosen), survey_choice=actual,
                          arms={arm: coverage(probes, owners, chosen) for arm, owners in by_arm.items()}))
    if sum(row["survey_choice"] for row in pairs) != 1:
        raise ValueError("Expected the frozen pair exactly once")
    all_visits = {p["visit_index"] for p in stereo}
    return dict(full={arm: coverage(probes, owners, all_visits) for arm, owners in by_arm.items()}, pairs=pairs)


def run(output):
    configuration()
    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or set(system["threads"].values()) != {"1"}):
        raise RuntimeError("Use the serialized low-priority Gauss benchmark core")
    archives = pinned_aperture()
    cases = {}
    for case in ("DS30-0008", "south-containing"):
        native, _, _, expected, identity = inputs(case)
        owners = canonical_owners(native, archives[case]["full"], identity, expected)
        cases[case] = dict(input=identity, owner_digests=expected["owners"],
                           **pair_census(native["source"]["probes"], owners))
    write(output, dict(machine=system, aperture_sha256=APERTURE_SHA, cases=cases))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
