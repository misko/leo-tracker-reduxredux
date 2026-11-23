"""Reduce graph-disrupting 8 ms additions without orbital fits or position search."""

import argparse
from collections import defaultdict
from itertools import chain, zip_longest
from math import remainder
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import RELEASE, configuration, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from eight_ms_crossover import CASE_ROOTS, originals, projected, strata
from local_future_policy import TRACKS_SHA256


MAX_FITS = 160
MAX_CPU_S = 35


def signature(tracks, within=None):
    group = []
    for curved, observation_ids in tracks:
        ids = frozenset(observation_ids)
        if within is not None:
            ids &= within
        if ids:
            group.append((curved, tuple(sorted(ids))))
    return tuple(sorted(group))


def minimize(options, matches):
    """Complement-first ddmin, stopping once no single deletion succeeds."""
    current = tuple(options)
    partitions = 2
    while current:
        width = (len(current) + partitions - 1) // partitions
        for first in range(0, len(current), width):
            cut = current[:first] + current[first+width:]
            if matches(cut):
                current = cut
                partitions = max(2, partitions - 1)
                break
        else:
            if width == 1:
                break
            partitions = min(len(current), partitions * 2)
    return current


def lane_key(row):
    return row["actual_rf_hz"], row["receiver"], row["channel"]


def lane_rows(observations):
    streams = defaultdict(list)
    for row in observations:
        streams[lane_key(row)].append(row)
    return streams


def feature(row, chronological, config):
    same_horizon = []
    for peer in chronological:
        delta = row["time_s"] - peer["time_s"]
        if .15 <= delta <= config.max_gap_s:
            speed = remainder(row["measured_cfo_hz"] - peer["measured_cfo_hz"], config.alias_spacing_hz) / delta
            same_horizon.append(abs(speed) <= config.max_slope_hz_s)
    return dict(prior_rows=len(same_horizon), legal_predecessors=sum(same_horizon), in_density_cap=len(same_horizon)>48)


def antecedents(by_lane, candidates, config):
    features = {row["observation_id"]: feature(row, rows, config) for rows in by_lane.values() for row in rows}
    wanted = {oid: features[oid] for oid in candidates}
    clock = dict(maximum_prior_rows=max((item["prior_rows"] for item in features.values()), default=0),
                 cap_targets=sum(item["in_density_cap"] for item in features.values()))
    return wanted, clock


class BudgetExceeded(Exception):
    pass


class GraphBuild:
    def __init__(self, config, *, max_fits=MAX_FITS):
        self.config = config
        self.max_fits = max_fits
        self.fits = 0
        self.cpu, self.started = process_time(), perf_counter()

    def __call__(self, rows, *, trace=None):
        from leo.analysis import graph_tracklets
        from leo.analysis.localization_v3.tracks import active_curvature, graph_tracks

        if self.fits >= self.max_fits or process_time()-self.cpu >= MAX_CPU_S:
            raise BudgetExceeded("Reached frozen graph-evaluation budget")
        self.fits += 1
        if trace is None:
            tracks = graph_tracks(rows, self.config)[0]
        else:
            identities = {row["time_s"]: row["observation_id"] for row in rows}
            original = graph_tracklets._path_models

            def path_models(t, y, path, lifted, available, cfg, depth=0):
                fitted = original(t, y, path, lifted, available, cfg, depth)
                if depth == 0:
                    trace.append(dict(path=[identities[t[i]] for i in path],
                                      proposals=[[identities[t[i]] for i in model["indices"]] for model in fitted]))
                return fitted

            with patch.object(graph_tracklets, "_path_models", path_models):
                tracks = graph_tracks(rows, self.config)[0]
        return signature((active_curvature(track), track["observation_ids"]) for track in tracks)

    def clocks(self):
        return dict(fits=self.fits, cpu_s=process_time()-self.cpu, elapsed_s=perf_counter()-self.started)


def first_divergence(base, counterfactual, added):
    for index, (a, b) in enumerate(zip_longest(base, counterfactual)):
        if a != b:
            new_path = [] if b is None else [oid for oid in b["path"] if oid in added]
            new_proposed = [] if b is None else [oid for oid in chain.from_iterable(b["proposals"]) if oid in added]
            return dict(path_index=index+1, base=a, modified=b, added_in_path=new_path, added_in_polynomial=new_proposed)
    return None


def reduce_lane(base, extras, expected, build):
    before, after = [], []
    base_graph = build(base, trace=before)
    full_graph = build(base+extras, trace=after)
    if full_graph != expected or base_graph == expected:
        raise ValueError("Expected an independently reproduced changed RF lane")
    old = frozenset(row["observation_id"] for row in base)
    extra_rows = {row["observation_id"]: row for row in extras}
    all_ids = tuple(extra_rows)
    cache = {(): base_graph, all_ids: full_graph}

    def evaluate(ids):
        if ids not in cache:
            cache[ids] = build(base + [extra_rows[oid] for oid in ids])
        return cache[ids]

    def equality(ids):
        return evaluate(ids) == expected

    minimum = minimize(all_ids, equality)
    complement = tuple(oid for oid in all_ids if oid not in minimum)
    direct_ids = frozenset(chain.from_iterable(ids for _, ids in full_graph)) & extra_rows.keys()
    directly = tuple(oid for oid in all_ids if oid in direct_ids)
    rejected = tuple(oid for oid in all_ids if oid not in direct_ids)
    contextual = {}
    for name, ids in (("direct_only", directly), ("rejected_only", rejected), ("full_complement", complement)):
        value = evaluate(ids)
        contextual[name] = dict(count=len(ids), full_target=value == full_graph,
                                old_lane_target=signature(value, old) == signature(full_graph, old),
                                old_lane_baseline=signature(value, old) == signature(base_graph, old))
    necessity = {oid: dict(in_reduced=not equality(tuple(x for x in minimum if x != oid)),
                           in_full=not equality(tuple(x for x in all_ids if x != oid))) for oid in minimum}
    if not all(item["in_reduced"] for item in necessity.values()):
        raise ValueError("Reduced graph retains a locally redundant lane")
    reduced_trace = []
    achieved = build(base + [extra_rows[oid] for oid in minimum], trace=reduced_trace)
    features = {oid: feature(extra_rows[oid], base+extras, build.config) for oid in minimum}
    return dict(additions=len(extras), available_base=len(base), direct_graph_factors=list(directly),
                reduced=[dict(oid=oid, in_full_graph=oid in direct_ids, time_s=extra_rows[oid]["time_s"],
                              fractional_margin=extra_rows[oid]["fractional_margin"], **features[oid]) for oid in minimum],
                contextual=contextual, one_removal_necessity=necessity,
                first_full_divergence=first_divergence(before, after, extra_rows),
                first_reduced_divergence=first_divergence(before, reduced_trace, extra_rows),
                distinct_graph_evaluations=len(cache)), achieved


def observed(crossover, name):
    details, = read(crossover / name / "joint-research-receipt.json")["solve"]["preparation"]
    return signature((track["curved"], track["ids"]) for track in details["tracks"])


def audit(case, crossover, output):
    system = host()
    publication, spec = configuration()
    publication._checked_graph_path(spec)
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths

    _, _, (twelve, eight) = originals(case)
    rows = strata(twelve, eight)
    added = {oid for oid, kind, *_ in rows if kind == "eight_only"}
    full_packet = dict(twelve, source=dict(twelve["source"], probes=projected(rows, "010")))
    base_by_lane = lane_rows(winning_observations(twelve)[0])
    all_by_lane = lane_rows(winning_observations(full_packet)[0])
    eight_by_lane = lane_rows(winning_observations(eight)[0])
    cfg = TrackConfig(**read(checked(RELEASE / "assets/tracks.json", TRACKS_SHA256))["config"])
    build = GraphBuild(cfg)
    prior, density = antecedents(all_by_lane, added, cfg)
    eight_prior, eight_density = antecedents(eight_by_lane, added, cfg)
    complete, changes = True, []
    with native_paths(Path(spec["graph_path"]["library"]), required=True) as native:
        baseline, full = {}, {}
        for key, observations in sorted(all_by_lane.items()):
            base = base_by_lane[key]
            candidate = [row for row in observations if row["observation_id"] in added]
            if len(base) + len(candidate) != len(observations):
                raise ValueError("Expected identical original measurements plus eight-only graph rows")
            baseline[key] = build(base)
            full[key] = build(observations) if candidate else baseline[key]
        original, target = tuple(sorted(chain.from_iterable(baseline.values()))), tuple(sorted(chain.from_iterable(full.values())))
        if original != observed(crossover, "000") or target != observed(crossover, "010") or len(prior) != len(added):
            raise ValueError("Graph-only endpoints do not reproduce the original prepared partitions")
        recreated = dict(baseline)
        for key in full:
            if baseline[key] == full[key]:
                continue
            try:
                addition = [row for row in all_by_lane[key] if row["observation_id"] in added]
                summary, recreated[key] = reduce_lane(base_by_lane[key], addition, full[key], build)
                for row in summary["reduced"]:
                    row["actual_8ms_prior"] = eight_prior[row["oid"]]
                changes.append(dict(rf_hz=key[0], receiver=key[1], channel=key[2], **summary))
            except BudgetExceeded:
                complete = False
                break
    if complete and tuple(sorted(chain.from_iterable(recreated.values()))) != target:
        raise ValueError("Joint reduced additions do not reproduce the exact prepared topology")
    write(output, dict(case=case, machine=system, graph_path_sha256=spec["graph_path"]["sha256"],
                       graph_assets=TRACKS_SHA256, clocks=build.clocks(), native=dict(native), complete=complete,
                       additions=len(added), rms_and_position_not_recomputed=True, changed_lanes=changes,
                       target_graph_sha256=canonical_digest(target), baseline_graph_sha256=canonical_digest(original),
                       density_010=density, density_111=eight_density,
                       maximum_prior_candidates=max(f["prior_rows"] for f in prior.values()),
                       no_legal_predecessor=sum(f["legal_predecessors"] == 0 for f in prior.values()),
                       one_legal_predecessor=sum(f["legal_predecessors"] == 1 for f in prior.values()),
                       actual_8ms_no_legal_predecessor=sum(f["legal_predecessors"] == 0 for f in eight_prior.values())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASE_ROOTS)
    parser.add_argument("crossover", type=Path)
    parser.add_argument("output", type=Path)
    audit(**vars(parser.parse_args()))
