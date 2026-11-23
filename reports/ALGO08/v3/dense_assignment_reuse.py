"""Census exact reuse across the original dense cold-rank candidates at their common site."""

import argparse
from collections import Counter
from contextlib import ExitStack
from functools import wraps
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from runpy import run_path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from aperture_trial import ARMS, archive_identity, configuration, read, solve, write
from cold_track_row_trial import SHARING, fit_evidence, rank_and_race
from cold_track_row_transfer import GEOGRAPHIC
from dense_full_short_crossover import TRACK_ASSET_PIN, file_sha
from dense_geographic_trial import host


SAVED = Path("/var/tmp/leo-v3-regional-dense-pair")
BINDING_PIN = "2d93dd6db50e0ff697fbfc33d69ebaceb0475a2ebf3296e7368a30e8c551d3cb"
CONTROL_PIN = "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"
REGIONAL = Path("/var/tmp/leo-regional-track.O238AD0C/scores.so")


def bits_same(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def arrays_sha(*values):
    digest = sha256()
    for array in values:
        array = np.asarray(array)
        digest.update(f"{array.dtype.str}:{array.shape}:".encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def column_names(model):
    hardware = [("hardware", k) for k in range(model.hardware.shape[1])]
    smooth = [("smooth", k) for k in range(model.smooth.shape[1])]
    phase = [("phase", int(k)) for k in model.labels]
    orbit = [("orbit", int(k), index) for k in model.supported for index in range(3)]
    constants = [("constant", row["component"]) for row in model.rows]
    return hardware + smooth + phase + orbit + constants


def capture(model, response, design, noise, groups, result):
    """Record the exact normalized inputs by original track and named parameter."""
    names = column_names(model)
    if (len(names) != design.shape[1] or len(response) != len(model.flat_times)
            or not model.keep.all() or len(result["noise_precision"]) != len(model.slices)):
        raise ValueError("Expected all retained rows in the original cold fit")
    blocks = {}
    for index, (row, alias, section) in enumerate(zip(model.rows, model.alias, model.slices, strict=True)):
        data = design[section]
        if not np.all(groups[section] == index):
            raise ValueError("The original native group would mix tracks")
        active = np.flatnonzero(np.any(data != 0., axis=0))
        cols = [names[k] for k in active]
        raw = model.values[section].copy()
        sigma = noise[section].copy()
        blocks[row["component"]] = dict(
            candidate=int(row["candidate_index"]), alias=int(alias), rows=len(raw), raw=raw, sigma=sigma,
            normalized_response=response[section] / sigma, final_weight=float(result["noise_precision"][index]),
            normalized_design={col: data[:, k] / sigma for col, k in zip(cols, active, strict=True)},
        )
    return dict(blocks=blocks, fixed_priors={name: float(p) for name, p in zip(
        names, result["coefficient_prior_precision"], strict=True)},
        coefficients={name: float(coef) for name, coef in zip(names, result["coefficient"], strict=True)},
        exact_call_sha256=arrays_sha(response, design, noise, groups))


def overlap(left, right):
    counts = Counter()
    a, b = left["blocks"], right["blocks"]
    for name in a.keys() & b.keys():
        x, y = a[name], b[name]
        if x["rows"] != y["rows"]:
            raise ValueError("Changed cold support within a common track")
        cols_x, cols_y = x["normalized_design"], y["normalized_design"]
        equal = {key for key in cols_x.keys() & cols_y.keys() if bits_same(cols_x[key], cols_y[key])}
        same_response = bits_same(x["normalized_response"], y["normalized_response"])
        same_assignment = (x["candidate"], x["alias"]) == (y["candidate"], y["alias"])
        same_block = equal == cols_x.keys() == cols_y.keys() and same_response
        count = x["rows"]
        counts.update(common_tracks=1, common_rows=count, same_assignment=int(same_assignment),
                      same_assignment_rows=count * same_assignment, same_raw_rows=count * bits_same(x["raw"], y["raw"]),
                      same_sigma_rows=count * bits_same(x["sigma"], y["sigma"]),
                      same_response_rows=count * same_response, same_group_statistics=int(same_block),
                      same_group_statistics_rows=count * same_block,
                      same_final_weight=int(x["final_weight"] == y["final_weight"]),
                      same_block_and_final_weight=int(same_block and x["final_weight"] == y["final_weight"]),
                      equal_named_active_design_columns=len(equal),
                      common_active_design_columns=len(cols_x.keys() & cols_y.keys()))
    for group, result in (("fixed_priors", "priors"), ("coefficients", "posterior_coefficients")):
        p, q = left[group], right[group]
        terms = p.keys() & q.keys()
        counts[result + "_common"] = len(terms)
        counts[result + "_exact"] = sum(p[key] == q[key] for key in terms)
        hardware = [key for key in terms if key[0] in ("hardware", "smooth")]
        if result == "posterior_coefficients":
            counts["radio_coefficients_common"] = len(hardware)
            counts["radio_coefficients_exact"] = sum(p[key] == q[key] for key in hardware)
    return dict(counts)


class Observer:
    def __init__(self):
        self.stage = "race"
        self.active = None
        self.counts = Counter()
        self.centres = {"rank": {}, "race": {}}
        self.race_positions = {}
        self.zero_phase_positions = {}

    def ranked_port(self, original):
        def wrap(ranker):
            run = original(ranker)

            @wraps(run)
            def observed(*args, **kwargs):
                self.stage = "rank"
                try:
                    return run(*args, **kwargs)
                finally:
                    self.stage = "race"

            return observed

        return wrap

    def normal(self, original, signature):
        @wraps(original)
        def evaluate(model, point):
            key = signature(dict(seed=dict(rows=model.rows), aliases=model.alias))
            xy = tuple(map(float, point))
            cold = bool(not np.any(model.reference))
            self.active = model, key, xy, cold
            if self.stage == "race":
                self.race_positions.setdefault(key, set()).add(xy)
                if cold:
                    self.zero_phase_positions.setdefault(key, set()).add(xy)
            try:
                return original(model, point)
            finally:
                self.active = None

        return evaluate

    def bound(self, original):
        def observed(instance, *args, **kwargs):
            key = self.stage + ("_normal" if self.active is not None else "_other")
            before = instance.counts["activated"]
            stamp = process_time_ns()
            result = original(instance, *args, **kwargs)
            self.counts[key + "_cpu_ns"] += process_time_ns() - stamp
            self.counts[key + "_calls"] += 1
            self.counts[key + "_native"] += instance.counts["activated"] - before
            self.counts[key + "_precision_updates"] += result["precision_iterations"]
            if self.active is not None:
                model, signature, xy, cold = self.active
                if cold and xy == (0., 0.) and signature not in self.centres[self.stage]:
                    if kwargs or len(args) != 4:
                        raise ValueError("Expected the original normal-prior cold likelihood inputs")
                    self.centres[self.stage][signature] = capture(model, *args, result)
            return result

        return observed

    def summarize(self, ranks):
        keys = [tuple(tuple(row) for row in candidate["signature"]) for candidate in ranks]
        if set(keys) != self.centres["rank"].keys() or set(keys[:3]) != self.centres["race"].keys():
            raise ValueError("Expected original centre likelihoods for all ranked assignments and three finalist starts")
        centres = self.centres["rank"]
        comparisons = [dict(ranks=[a + 1, b + 1], **overlap(centres[keys[a]], centres[keys[b]]))
                       for a, b in combinations(range(len(keys)), 2)]
        return dict(counts=dict(self.counts), centre_comparisons=comparisons,
                    finalist_centre_call_reuse=[centres[k]["exact_call_sha256"] == self.centres["race"][k]["exact_call_sha256"]
                                                for k in keys[:3]],
                    finalist_sites=[len(self.race_positions[k]) for k in keys[:3]],
                    pairwise_common_trial_sites=[len(self.race_positions[a] & self.race_positions[b])
                                                 for a, b in combinations(keys[:3], 2)],
                    pairwise_common_zero_phase_trial_sites=[len(self.zero_phase_positions[a] & self.zero_phase_positions[b])
                                                 for a, b in combinations(keys[:3], 2)])


def ceilings(control, target=16.):
    stages = control["route_details"]
    full = control["solve"]["cpu_s"]
    cold = stages["cold_clocks"]["cpu_s"]
    broad = cold + stages["salvage_clocks"]["cpu_s"] + stages["predictive_clocks"]["cpu_s"]
    return dict(archived_full_solve_cpu_s=full, target_cpu_s=target, saving_required_cpu_s=full-target,
                free_complete_cold_stage_saving_cpu_s=cold, remaining_with_free_cold_cpu_s=full-cold,
                remaining_with_free_cold_salvage_and_predictive_cpu_s=full-broad,
                fine_alternative_profile_calls=stages["certified_salvage"]["profile_calls"],
                all_salvage_support_trials=stages["certified_salvage"]["support_trials"])


def run(output):
    machine = host()
    publication, specification = configuration()
    from blind_rank_trial import timer
    from early_region import before_fit
    from full_short_raw import RECIPE_SHA
    from full_short_run import geographic_projection
    from leo.analysis.localization_v3 import discovery, position
    from leo.analysis.localization_v4.native_bound import NativeBound
    from leo.contracts.digests import canonical_digest
    from prepared_exterior import handoff
    import proof_global_rank
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    binding_path, control_path = SAVED / "binding.json", SAVED / "native/joint-research-receipt.json"
    if file_sha(binding_path) != BINDING_PIN or file_sha(control_path) != CONTROL_PIN:
        raise ValueError("The sealed native regional control changed")
    binding, control = read(binding_path), read(control_path)
    receipt = control["receipt"]
    folder = SAVED / "native/fast-scan-automatic-work"
    packet_path, = folder.glob("*/detections.json")
    native = read(packet_path)
    terminal = read(folder / receipt["run_id"] / "terminal.json")
    archive, offer = Path(binding["archive"]["root"]), binding["offer"]
    if (control["route"] != "complete" or terminal["region"] != offer
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or "sha256:" + file_sha(packet_path) != terminal["native_sha256"]
            or terminal["native_sha256"] != binding["packet_sha256"]
            or native["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA
            or archive_identity(archive) != binding["archive"]):
        raise ValueError("Saved input, receiver, terrain offer or causal archive changed")
    metrics, regional = {}, []
    observer = Observer()
    share = run_path(str(SHARING))["shared_rank_preparation"]
    stored_solve = algo08_position.solve

    def census(prepared, region, bound, _stages, **_options):
        with ExitStack() as scope:
            scope.enter_context(patch.object(proof_global_rank, "rank_port", observer.ranked_port(proof_global_rank.rank_port)))
            scope.enter_context(patch.object(position.NormalPosition, "calculate", observer.normal(position.NormalPosition.calculate,
                                                                                                  discovery.signature)))
            scope.enter_context(patch.object(NativeBound, "__call__", observer.bound(NativeBound.__call__)))
            timer(scope, discovery.DiscoveryPosition, "calculate", observer.counts, key="rank_discovery_calculate")
            metrics.update(rank_and_race(prepared, region, bound, True, share))
        return dict(status="withheld", reason="cold_assignment_census_complete", arms={arm: {"latlon": None} for arm in ARMS})

    def observed(document, reader, assets, region):
        if document is not native or reader.root != archive or region.document() != offer or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN:
            raise ValueError("The signed dense packet, graph or region changed before solving")
        with ExitStack() as scope:
            scope.enter_context(geographic_projection(GEOGRAPHIC, REGIONAL))
            live, _, _ = scope.enter_context(handoff(reader))
            before = before_fit(census, reader, regional_bound_guard.causal_probes, regional, live.match)
            scope.enter_context(patch.object(v5_core, "infer", before))
            return stored_solve(document, reader, assets, region)

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, specification, native, archive, offer)
    archived = control["route_details"]["cold"]
    checks = dict(archived_winner=fit_evidence({key: metrics["branch"][key] for key in archived}) == fit_evidence(archived),
                  route=result["reason"] == "cold_assignment_census_complete", archive=archive_identity(archive) == binding["archive"])
    if not all(checks.values()):
        raise ValueError(f"Original cold route changed: {checks}")
    ranks = metrics["records"]
    details = observer.summarize(ranks)
    write(output, dict(checks=checks, host=machine, input_sha256=binding["packet_sha256"], control_sha256=CONTROL_PIN,
                       archive=binding["archive"], offer=offer, ordered_rank_scores=[row["score"] for row in ranks],
                       cold_race=metrics["branch"], discovery_attribution=metrics["attribution_ns"], matched=details,
                       ceilings=ceilings(control), driver_sha256=file_sha(Path(__file__))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
