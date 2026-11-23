"""Measure a full-recording hindsight owner-only selector on sealed native data."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, write
from primary_owner_census import APERTURE_SHA, canonical_owners, functions, pinned_aperture


CASES = ("DS30-0008", "south-containing", "south-far")
WIDTH = 12
MAX_AGE = 80_000_000
MIN_AGE = 4_000_000
CONTINUATION_SHA256 = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"


def histories(probes, selected):
    """Find every relevant preceding opportunity by the released lane identity."""
    past = defaultdict(lambda: deque(maxlen=WIDTH))
    windows = {}
    for index, row in enumerate(probes):
        key = tuple(row[name] for name in ("receiver_id", "channel", "actual_rf_hz"))
        counter = row["valid_start_counter"]
        lane = past[key]
        if lane and lane[-1][1] >= counter:
            raise ValueError("Receiver/channel/RF opportunities must be chronological")
        if index in selected:
            windows[index] = tuple(i for i, when in lane if counter - when <= MAX_AGE)
        lane.append((index, counter))
    if set(windows) != set(selected):
        raise ValueError("An ownership lane is outside the sealed packet")
    return windows


def necessary_donors(probes, kept, windows):
    """Exact unit-cost minimum for the ideal three-donor interval demands."""
    requirements = []
    for target, window in windows.items():
        now = probes[target]["valid_start_counter"]
        old = tuple(i for i in window if now - probes[i]["valid_start_counter"] >= MIN_AGE)
        requirements.extend(((window, 3), (old, 1)))
    if any(len(window) < demand for window, demand in requirements):
        raise ValueError("An original selected lane lacks the required history opportunities")
    paid = set(kept)
    for window, demand in sorted(requirements, key=lambda item: item[0][-1]):
        deficit = demand - sum(i in paid for i in window)
        if deficit > 0:
            available = [i for i in window if i not in paid]
            paid.update(available[-deficit:])
    return paid


def observed_donors(probes, kept, windows, votes):
    """Greedy surrogate using published single factors, with full history when unresolved."""
    paid = set(kept)
    certifiable = 0
    charged_full = 0
    candidates = [tuple(f["fractional_tracking_cfo_hz"] for f in row["candidates"]) for row in probes]
    times = [row["valid_start_counter"] for row in probes]
    for target, previous in windows.items():
        hz, = candidates[target]
        donors = tuple(i for i in previous if candidates[i])

        def supports(indices):
            return votes(hz, [(times[i], candidates[i]) for i in indices], times[target]) >= 3

        if not supports(donors):
            charged_full += 1
            paid.update(previous)
            continue
        certifiable += 1
        active = tuple(i for i in donors if i in paid)
        if supports(active):
            continue
        remaining = tuple(i for i in reversed(donors) if i not in paid)
        selected = next(extra for size in range(1, 4) for extra in combinations(remaining, size)
                        if supports(sorted((*active, *extra))))
        paid.update(selected)
    return paid, dict(witnessed=certifiable, full_window_charged=charged_full)


def price(native, kept):
    from tools.pipeline_eval.variants import carrier_continuation
    from leo.contracts.digests import canonical_digest

    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != CONTINUATION_SHA256:
        raise ValueError("Continuation differs from the reviewed released source")
    if native["source"]["sample_rate_hz"] != 10_000_000:
        raise ValueError("Continuation donor geometry requires the original sample clock")
    probes = native["source"]["probes"]
    windows = histories(probes, kept)
    full = set(kept).union(*windows.values())
    lower = necessary_donors(probes, kept, windows)
    proxy, witnessed = observed_donors(probes, kept, windows, carrier_continuation.votes)
    if not (len(kept) <= len(lower) <= len(proxy) <= len(full) and lower <= full and proxy <= full):
        raise ValueError("Donor counts do not satisfy the retained and full-window limits")

    def describe(indices):
        bands = Counter(tuple(probes[i][field] for field in ("receiver_id", "edge", "channel", "actual_rf_hz"))
                        for i in indices)
        return dict(lanes=len(indices), archived_selected_rank=dict(sorted(Counter(
            str(probes[i]["candidates"][0]["candidate_rank"])
            for i in indices if probes[i]["candidates"]).items())),
            lane_sha256=canonical_digest(sorted(indices)), rf_lane_counts=[[*key, count] for key, count in sorted(bands.items())])

    return dict(admitted=describe(range(len(probes))), owned_only=describe(kept),
                ideal_donor_floor=describe(lower), exported_donor_proxy=describe(proxy),
                full_original_donor_window=describe(full), exported_donor_compatibility=witnessed)


def owner_mask(native, kept):
    from leo.contracts.digests import canonical_digest

    src = native["source"]
    original = src["probes"]
    if any(i < 0 or i >= len(original) or len(original[i]["candidates"]) != 1 for i in kept):
        raise ValueError("The owner selector requires an original admitted selected factor")
    rows = [probe if i in kept else dict(probe, candidates=[]) for i, probe in enumerate(original)]
    receiver = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    digest = canonical_digest(["cancellation", src["raw_recording_authority_digest"], receiver, rows])
    return dict(native, source=dict(src, probes=rows, analysis_manifest_sha256=digest),
                provenance=dict(native["provenance"], run_id="blind-compact-" + digest[7:39]))


def prepared_summary(prepared):
    from leo.contracts.digests import canonical_digest
    from leo.application.localization_v3_engine import _prepared_values

    values = _prepared_values(prepared)
    tracks = values.get("tracks", {})
    curves = tracks.get("curved_indices", [])
    return dict(status=values["status"], observations=len(tracks.get("observations", [])),
                graph_points=tracks.get("graph_points"), tracks=len(tracks.get("tracks", [])),
                curved_tracks=len(curves), curved_points=sum(len(tracks["tracks"][i]["observation_ids"]) for i in curves),
                track_membership_sha256=canonical_digest(sorted(
                    sorted(row["observation_ids"]) for row in tracks.get("tracks", [])
                )))


def solve(publication, spec, native, archive, offer, *, prepare_only):
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core

    from mixture_trial import elapsed, summarize

    prep, ranking = [], []

    def analyze(_recording, _root, assets, archive_root, region):
        prepare = algo08_position.prepare_native_scan
        rank = v5_core.ranked_initial_nodes

        def observed(*args, **kwargs):
            value = prepare(*args, **kwargs)
            prep.append(prepared_summary(value))
            return value

        def discover(scan):
            from leo.analysis.localization_v3.discovery import signature
            from leo.contracts.digests import canonical_digest

            nodes = rank(scan)
            ranking.append(dict(branches=len(nodes), catalogue=len(scan.norads),
                                ranked_signatures_sha256=canonical_digest([signature(n) for n in nodes])))
            return nodes

        def prepared(*_args, **_kwargs):
            return dict(status="inputs_only", reason=None, arms={})

        cpu, wall = process_time(), perf_counter()
        inference = prepared if prepare_only else v5_core.infer
        with (patch.object(algo08_position, "prepare_native_scan", observed),
              patch.object(v5_core, "ranked_initial_nodes", discover),
              patch.object(v5_core, "infer", inference)):
            decision, packet, policy = algo08_position.solve(native, TleArchiveReader(archive_root), assets, region)
        charged = elapsed(cpu, wall)
        result, owners = summarize(decision, packet, policy)
        grid = None if packet is None else packet["position_grid"]
        return dict(result=result, owners=owners, preparation=prep, discovery=ranking, metrics=decision.get("metrics"),
                    numerical_grid_complete=None if grid is None else grid["complete"], charged=charged)

    with TemporaryDirectory() as directory:
        root = Path(directory)
        offer_path = root / "offer.json"
        offer_path.write_text(json.dumps(offer))
        destination = root / "output"
        destination.mkdir()
        args = SimpleNamespace(recording=root / "saved", bulk_root=destination, archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            return publication.run(args, spec)


def trial(case, output, *, prepare_only=False):
    publication, spec = configuration()
    from leo.contracts.digests import canonical_digest

    native, archive, offer, stock, identity = inputs(case)
    mask_case = "south-containing" if case == "south-far" else case
    authority, _, _, containing, binding = inputs(mask_case)
    if native != authority:
        raise ValueError("The omitted offer needs the exact containing waveform and detector bytes")
    archived = pinned_aperture()[mask_case]["full"]
    owners = canonical_owners(authority, archived, binding, containing)
    keep = set().union(*(set(owners[arm]) for arm in ARMS))
    pricing = price(native, keep)
    masked = owner_mask(native, keep)
    _, winning_observations, _ = functions()
    masked_rows, _ = winning_observations(masked)
    expected_ids = {row["observation_id"] for arm in ARMS for row in owners[arm].values()}
    if len(masked_rows) != len(keep) or {row["observation_id"] for row in masked_rows} != expected_ids:
        raise ValueError("Owner union no longer has the original signed observation identities")
    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(value != "1" for value in system["threads"].values())):
        raise ValueError("Expected the declared low-priority one-core worker")
    result = solve(publication, spec, native if prepare_only else masked, archive, offer, prepare_only=prepare_only)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the replay")
    result.update(case=case, identity=identity, full_owner_packet_sha256=APERTURE_SHA, mask_authority=binding,
                  masked_packet_sha256=canonical_digest(masked), price=pricing,
                  masked_observations=len(masked_rows), full_v3=stock,
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), machine=system)
    write(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    trial(**vars(parser.parse_args()))
