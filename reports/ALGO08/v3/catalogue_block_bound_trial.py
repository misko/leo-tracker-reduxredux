"""Audit catalogue block ambiguity inside the original cached saved cold rank."""

import argparse
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
OLD = Path("/dev/shm/leo-v3-cold-exact-budget/reports/ALGO08/v3")
BASE = Path("/dev/shm/leo-v3-cold-exact-budget-run")
PROFILE = "b274c063df2a39b76bedc00d146e4896fe6047b07b960cea5e9f6904976d0f0d"
BASELINES = dict(medium="ede8de8343902f962166ec3078a01275c39ffbb2306256ad81354670cef26ead",
                 dense="d5caefcf59182ded8f26176b2548e03a6d814d89dca98f081bc57e765600757d")
COLD_DRIVER = "7c74210ab8cb6bd6c610860e64108a0cc63e1c25267d453d8cdbe2cb8df07ca9"
SCAN_PIN = "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89"
WHITE_PIN = "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf"
SPARSE_PIN = "e381e0807e47a10091ffd9c9d1d8c0d43aa531a5e4c81acda53ddbfa922ef021"


def read_checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Saved evidence or stage source changed at {path}")
    return body


def archived():
    sys.path[:0] = [str(OLD), str(HERE)]
    read_checked(OLD/"cold_exact_budget.py", COLD_DRIVER)
    import cold_exact_budget

    if Path(cold_exact_budget.__file__) != OLD/"cold_exact_budget.py":
        raise ValueError("Use the original saved worker and fitted stage controls")
    return cold_exact_budget


class RankComplete(BaseException):
    """Leave the controlled worker before finalist fits and publication."""


def reject_fallback(*_args, **_kwargs):
    raise RuntimeError("The saved rank census cannot proceed to a full solver")


@contextmanager
def observe_curves(scan, audit):
    import numpy as np
    import catalogue_block_bound as block
    from leo.analysis.localization_v3 import scan as kernel
    from leo.analysis.research import retained_track_likelihood as white
    from tools.pipeline_eval.variants import algo08_sparse_rank_projection as sparse

    for module, digest in ((kernel, SCAN_PIN), (white, WHITE_PIN), (sparse, SPARSE_PIN)):
        read_checked(Path(module.__file__), digest)
    if kernel.profile is not white.profile or scan.curve.__func__ is not kernel.ScanLikelihood.curve:
        raise ValueError("White profile or curve was replaced")
    original, predict = scan.curve, scan.predictions
    counts, elapsed, histogram = Counter(), Counter(), Counter()
    phase, atlas, cached = None, None, {}
    per_call = []

    def predictions(*args, **kwargs):
        nonlocal phase
        phase = predict(*args, **kwargs)
        counts["prediction_calls"] += 1
        return phase

    def curve(i, observed, predicted, method, **options):
        nonlocal atlas
        t0 = process_time_ns()
        terms = original(i, observed, predicted, method, **options)
        baseline = process_time_ns()-t0
        elapsed["original_curve"] += baseline
        counts["curve_calls"] += 1
        counts["rows"] += len(predicted)
        counts["cells"] += predicted.size
        start = process_time_ns()
        sampled = block.sample_indices(len(observed))
        if (phase is None or sampled is None or method not in ("shared_phase", "receiver_smooth") or options
                or type(phase[0]) is not sparse.ProjectedRows or type(phase[1]) is not sparse.ProjectedRows
                or phase[0].changed_rows is not phase[1].changed_rows or not block.white_domain(observed)):
            counts["fallback_calls"] += 1
            elapsed["eligibility"] += process_time_ns()-start
            return terms
        frequency, elevation, _ = phase
        if atlas is not frequency.base:
            atlas = frequency.base
            cached.clear()
            counts["atlas_generations"] += 1
        columns = scan.index[i]
        scale = scan.tracks[i]["rf_hz"] / 11.5e9
        if i not in cached:
            picked = columns[sampled]
            cached[i] = block.nominal_blocks(scale*frequency.base[:, picked], elevation.base[:, picked], sampled)
            counts["index_builds"] += 1
            counts["index_sample_cells"] += len(predicted)*len(sampled)
        else:
            counts["index_hits"] += 1
        index = cached[i]
        elapsed["index_and_eligibility"] += process_time_ns()-start
        if index is None:
            counts["fallback_calls"] += 1
            return terms

        start = process_time_ns()
        # This duplicate all-row visibility gather exists only in the observer.
        visible = (elevation.base[:, columns] >= 0.).all(axis=1)
        visible[elevation.changed_rows] = (elevation.values[:, columns] >= 0.).all(axis=1)
        protected, cutoff = block.exact_protected(visible, terms)
        if protected is None:
            counts["fallback_calls"] += 1
            elapsed["oracle_visibility_and_all_costs"] += process_time_ns()-start
            return terms
        shifted = np.zeros(len(visible), dtype=bool)
        shifted[frequency.changed_rows] = True
        nominal = ~shifted[index.rows]
        members = np.add.reduceat(nominal, index.starts)
        block_sizes = np.diff(np.r_[index.starts, len(index.rows)])
        whole = members == block_sizes
        row_zero = np.logical_or.reduceat(index.rows == 0, index.starts)
        available = (members > 0) & ~row_zero
        protected_count = np.add.reduceat(protected[index.rows] & nominal, index.starts)
        actual_ambiguity = np.add.reduceat(protected[index.rows], index.starts)
        for value, n in enumerate(np.bincount(actual_ambiguity)):
            histogram[value] += int(n)
        oracle = (protected_count == 0) & available
        horizon = index.horizon_excluded() & available
        elapsed["oracle_visibility_and_all_costs"] += process_time_ns()-start

        start = process_time_ns()
        squared = index.lower(observed)
        using_oracle = block.reject_blocks(index, squared, cutoff, len(observed)) & available
        row, upper = block.independent_incumbent(index, squared, observed, shifted, frequency.base,
                                                elevation.base, columns, scale)
        feasible = block.reject_blocks(index, squared, upper, len(observed)) & available
        elapsed["query_and_incumbent"] += process_time_ns()-start
        if ((feasible & ~using_oracle).any() or (using_oracle & (protected_count > 0)).any()
                or (row is not None and np.isfinite(upper) and (not visible[row] or upper < terms["cost"][row]))):
            raise ValueError("Grouped screen would erase an original paid association competitor")
        counts.update(eligible_calls=1, blocks=len(members), shifted_rows=int(shifted.sum()),
                      visible_rows=int(visible.sum()), protected_rows=int(protected.sum()),
                      available_rows=int(members.sum()), shifted_only_blocks=int((members == 0).sum()),
                      wholly_nominal_blocks=int(whole.sum()),
                      finite_oracle=int(np.isfinite(cutoff)), finite_independent=int(np.isfinite(upper)))
        recorded = {}
        for key, mask in (("oracle", oracle), ("using_oracle_cutoff", using_oracle), ("feasible", feasible), ("horizon", horizon)):
            rows = int(members[mask].sum())
            counts.update({key+"_blocks": int(mask.sum()), key+"_whole_blocks": int((mask & whole).sum()),
                           key+"_rows": rows, key+"_cells": rows*len(observed)})
            # Cost apportioned by row count is an optimistic model. The actual call is still paid.
            if rows == len(predicted):
                elapsed[key+"_whole_call_savings"] += baseline
            elapsed[key+"_linear_row_model"] += baseline * rows // len(predicted)
            recorded[key] = rows
        per_call.append(dict(track=int(i), points=len(observed), method=method, roster=len(predicted),
                             blocks=len(members), original_curve_cpu_ns=baseline, protected=int(protected.sum()),
                             shifted=int(shifted.sum()), removed_rows=recorded))
        return terms

    with patch.object(scan, "predictions", predictions), patch.object(scan, "curve", curve):
        yield
    audit.update(counts=dict(counts), cpu_ns=dict(elapsed), protected_per_group=dict(sorted(histogram.items())), calls=per_call)


def worker(case, request, inventory, output, *, prototype=False):
    original = archived()
    expected = json.loads(read_checked(BASE/(case+"-control")/"result.json", BASELINES[case]))
    result = {}

    @contextmanager
    def capture(profiled):
        import cold_finalist_race
        import joint_publication as joint
        from leo.analysis.localization_v3.discovery import signature
        from tools.pipeline_eval.variants import v5_core

        def census(prepared, region, bound):
            from blind_joint_finish import digest

            start = process_time_ns(), perf_counter_ns()
            scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
            if len(scan.norads) != expected["stages"]["work"]["selected"]["catalogue"]:
                raise ValueError("Archived cold catalogue extent changed")
            # The archived full-catalogue route already wraps this callable
            # with its actual centre tables, scratch and repeat caches.
            if prototype:
                ranked, paired = paired_rank(prepared, region, bound, scan, v5_core)
                result["paired"] = paired
            else:
                with observe_curves(scan, result):
                    ranked = v5_core.ranked_initial_nodes(scan)
            signatures = [[list(row) for row in signature(node)] for node in ranked]
            if signatures != expected["stages"]["work"]["ordered"]:
                raise ValueError("The exact instrumented rank disagrees with the sealed input")
            result.update(cold_rank_plus_observer=dict(cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1]),
                          ordered_ranks=len(signatures), exact_archived_signatures=True,
                          prior_cold_row_cache=expected["solve"]["cold_track_rows"],
                          prior_rank=expected["stages"]["work"]["ranks"][0], other_position_solves=0, waveform_reads=0)

        def stop(_mode, prepared, region, bound):
            try:
                census(prepared, region, bound)
            except Exception as error:
                raise RuntimeError("The catalogue block audit failed inside the rank") from error
            raise RankComplete

        full_route = joint.full_catalogue_route

        def guarded_route(_installed, *args, **options):
            return full_route(reject_fallback, *args, **options)

        if profiled:
            raise ValueError("Use unprofiled original install scope")
        with (patch.object(cold_finalist_race, "refine", stop),
              patch.object(joint, "full_catalogue_route", guarded_route)):
            yield

    with patch.object(original, "controlled_cold", capture):
        try:
            original.worker(request, inventory, output, "control", case)
        except RankComplete:
            from aperture_trial import write
            if not result or any(output.glob("fast-scan-automatic-work/*/terminal.json")):
                raise ValueError("The census escaped the original pre-finalist boundary")
            write(output/"catalogue-blocks.json", result)
            return
    raise ValueError("The original rank was never reached")


def paired_rank(prepared, region, bound, scan, core):
    import catalogue_block_rank as prototype
    import cold_track_row_entry as entry
    from blind_joint_finish import digest
    from leo.analysis.localization_v3.discovery import signature
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from proof_global_rank import ranked_scores

    def timed(context):
        start = process_time_ns(), perf_counter_ns()
        nodes = core.ranked_initial_nodes(context)
        return nodes, dict(cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])

    def readout(nodes):
        return json.loads(json.dumps(nodes, default=_json_value, allow_nan=False))

    work = Counter()

    def install(current, tables, _global_counts, *, borrow=False):
        return prototype.install(current, tables, work, borrow=borrow)

    def closed(wrapper, name, qualified_name):
        if wrapper.__qualname__ != qualified_name:
            raise ValueError("The ordinary cached rank wrapper changed")
        cells = dict(zip(wrapper.__code__.co_freevars, wrapper.__closure__, strict=True))
        return cells[name].cell_contents

    track_rows = closed(core.ranked_initial_nodes, "ordinary_rank", "full_catalogue_route.<locals>.cold.<locals>.rank")
    installed = closed(track_rows, "original", "rank_with_centre_rows.<locals>.rank")
    with ranked_scores(installed):
        original_scored, baseline_clock = timed(scan)
        candidate_scan = core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
        with patch.object(entry, "shared_association_rows", install):
            candidate_scored, elapsed = timed(candidate_scan)
    original_scores, baseline = zip(*original_scored, strict=True)
    candidate_scores, candidate = zip(*candidate_scored, strict=True)
    base, test = readout(baseline), readout(candidate)
    original_digest, candidate_digest = canonical_digest(base), canonical_digest(test)
    scores_match = [float(x).hex() for x in original_scores] == [float(x).hex() for x in candidate_scores]
    changed = []
    for rank, (left, right) in enumerate(zip(base, test, strict=False), 1):
        for row1, row2 in zip(left["seed"]["rows"], right["seed"]["rows"], strict=False):
            if row1 != row2:
                changed.append(dict(rank=rank, curve=row1["component"], keys=sorted(k for k in row1 if row1[k] != row2[k])))
    return baseline, dict(control=baseline_clock, candidate=elapsed, cold_nodes_byte_equal=original_digest == candidate_digest,
                          ordered_signatures_match=[signature(node) for node in baseline] == [signature(node) for node in candidate],
                          all_rank_scores_exact=scores_match, original_scores=original_scores, candidate_scores=candidate_scores,
                          control_digest=original_digest, candidate_digest=candidate_digest,
                          changed_diagnostics=changed, candidate_work=dict(work))


def run(case, root, *, prototype=False):
    original = archived()
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if subprocess.check_output(["findmnt", "-T", root.parent, "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use a new tmpfs stage")
    request, inventory = original.assigned(case)
    baseline = json.loads(read_checked(BASE/(case+"-control")/"result.json", BASELINES[case]))
    profile = json.loads(read_checked(BASE/"profile/result.json", PROFILE))["stages"]["work"]["profile_rows"]
    root.mkdir()
    (root/"tmp").mkdir()
    path = root/"request.json"
    write(path, request)
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    output = root/"rank"
    command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", case, output, "--request", path, "--inventory", inventory]
    names = [Path(__file__).name, "catalogue_block_bound.py", "catalogue-block-bound-protocol.md"]
    if prototype:
        command.append("--prototype")
        names.append("catalogue_block_rank.py")
    write(root/"binding.json", dict(case=case, machine=host(), request=request, inventory=str(inventory),
                                    archived_driver=COLD_DRIVER, archived_control=BASELINES[case], archived_profile=PROFILE,
                                    prototype=prototype, source={name: sha256((HERE/name).read_bytes()).hexdigest() for name in names},
                                    archived_full_solve_cpu=baseline["solve"]["cpu_s"]))
    clock = measure(command, env, output)
    write(root/"clock.json", dict(clock=clock, command=list(map(str, command))))
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])
    if case == "dense":
        profile = [row for row in profile if row['function'] in ("association", "curve") and row["file"].endswith("/localization_v3/scan.py")]
    else:
        profile = []
    write(root/"result.json", dict(clock=clock, binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest(),
                                   rank=read(output/"catalogue-blocks.json"), historical_profile=profile))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("worker", "run"))
    cli.add_argument("case", choices=tuple(BASELINES))
    cli.add_argument("output", type=Path)
    cli.add_argument("--request", type=Path)
    cli.add_argument("--inventory", type=Path)
    cli.add_argument("--prototype", action="store_true")
    args = cli.parse_args()
    if args.mode == "worker":
        worker(args.case, args.request, args.inventory, args.output, prototype=args.prototype)
    else:
        run(args.case, args.output, prototype=args.prototype)
